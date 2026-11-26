import json
import logging
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager, contextmanager
from html import escape
from ipaddress import ip_address
from pathlib import Path
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from typing import Annotated
from urllib.parse import quote, urlencode, urlsplit

import anyio
import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

POST_HOSTS = frozenset(
    f"{prefix}{domain}"
    for domain in ("x.com", "twitter.com")
    for prefix in ("", "www.", "m.", "mobile.")
)
THUMBNAIL_HOSTS = frozenset({"pbs.twimg.com"})
MEDIA_HOSTS = THUMBNAIL_HOSTS | {"video.twimg.com"}
TWITTER_EXTRACTORS = "twitter,twitter:card,twitter:amplify,twitter:broadcast,twitter:spaces"
logger = logging.getLogger("uvicorn.error.xstream")
# Keep subprocess usage bounded on the single Render worker.
extraction_slots = BoundedSemaphore(2)
conversion_slots = BoundedSemaphore(1)
stream_slots = BoundedSemaphore(8)
MAX_MEDIA_BYTES = 128 * 1024 * 1024
MEDIA_SECONDS = 90
MAX_AUDIO_BYTES = 64 * 1024 * 1024
AUDIO_SECONDS = 180


class ClientBudget:
    def __init__(self):
        self.window = -1
        self.counts = {}
        self.lock = Lock()

    def retry_after(self, client: str, bucket: str, limit: int) -> int:
        now = int(monotonic())
        with self.lock:
            if self.window != now // 60:
                self.window = now // 60
                self.counts.clear()

            key = (client, bucket)
            count = self.counts.get(key, 0)
            if count >= limit or (count == 0 and len(self.counts) >= 4096):
                return 60 - now % 60
            self.counts[key] = count + 1
            return 0


def client_address(scope) -> str:
    peer = (scope.get("client") or ("unknown",))[0]
    try:
        address = ip_address(peer)
        # Render terminates public traffic at Cloudflare. Only its private ingress
        # may supply the edge-assigned address. Ignore arbitrary forwarded chains.
        if os.getenv("RENDER") == "true" and address.is_private:
            edge_client = Headers(scope=scope).get("cf-connecting-ip")
            if edge_client:
                return str(ip_address(edge_client))
        return str(address)
    except ValueError:
        return peer


class TrafficMiddleware:
    def __init__(self, app):
        self.app = app
        self.budget = ClientBudget()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        scope.setdefault("state", {})["traffic_budget"] = self.budget
        started = monotonic()
        status, sent_bytes, complete = 500, 0, False
        path, method = scope["path"], scope["method"]

        async def record(message):
            nonlocal status, sent_bytes, complete
            await send(message)
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                sent_bytes += len(message.get("body", b""))
                complete = not message.get("more_body", False)
            elif message["type"] == "http.response.pathsend":
                complete = True

        try:
            retry_after = 0
            if path == "/api/video" and method == "POST":
                retry_after = self.budget.retry_after(client_address(scope), "extraction", 12)
            elif method == "GET" and path in ("/api/preview", "/api/download", "/api/convert-mp3"):
                # Both audio aliases share a conversion budget.
                query = Request(scope).query_params
                is_audio = path == "/api/convert-mp3" or (
                    path == "/api/download" and query.get("url", "").startswith("mp3:")
                )
                bucket, limit = ("audio", 6) if is_audio else ("media", 60)
                retry_after = self.budget.retry_after(client_address(scope), bucket, limit)
            if retry_after:
                headers = {"Retry-After": str(retry_after), "Cache-Control": "no-store"}
                if path == "/api/download" and not is_audio and "post_url" in query:
                    keys = ("url", "post_url", "clip_id", "quality", "filename")
                    response = download_error_page(
                        HTTPException(429, "Too many downloads. Wait a minute and try again.", headers=headers),
                        {key: query[key] for key in keys if key in query},
                    )
                else:
                    response = JSONResponse(
                        {"detail": "Too many requests. Wait a minute and try again."}, status_code=429, headers=headers
                    )
                await response(scope, receive, record)
            else:
                await self.app(scope, receive, record)
        finally:
            route = getattr(scope.get("route"), "path", None)
            if route is None:
                route = path if path in ("/api/video", "/api/preview", "/api/download", "/api/convert-mp3", "/health", "/") else "unmatched"
            logger.info(
                "route=%s status=%d duration_ms=%d bytes=%d outcome=%s",
                route, status, (monotonic() - started) * 1000, sent_bytes, "complete" if complete else "interrupted",
            )


@asynccontextmanager
async def lifespan(_app):
    # Also protects existing native Uvicorn services until their start command is updated.
    logging.getLogger("uvicorn.access").disabled = True
    missing = [tool for tool in ("yt-dlp", "ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError("Missing required media tools: " + ", ".join(missing))
    yield


@contextmanager
def subprocess_slot(slots: BoundedSemaphore, detail: str):
    if not slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail=detail, headers={"Retry-After": "3"})
    try:
        yield
    finally:
        slots.release()


def normalize_allowed_url(url: str, hosts: frozenset[str], *, allow_http: bool = False) -> str | None:
    if not url or "\\" in url or any(char.isspace() or ord(char) < 32 for char in url):
        return None

    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if host not in hosts or parsed.username is not None or parsed.password is not None:
            return None
        if parsed.scheme == "https":
            default_port = 443
        elif allow_http and parsed.scheme == "http":
            default_port = 80
        else:
            return None
        if parsed.port not in (None, default_port):
            return None
    except ValueError:
        return None

    return parsed._replace(scheme="https", netloc=host, fragment="").geturl()


def validate_post_url(url: str) -> str:
    post_url = normalize_allowed_url(url.strip(), POST_HOSTS, allow_http=True)
    if post_url is None:
        raise ValueError("Enter a valid X or Twitter post link.")
    return post_url


def require_post_url(url: str) -> str:
    try:
        return validate_post_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

# --- Pydantic Models for API ---
# These models define the expected input and output JSON structure.
class DownloadOption(BaseModel):
    quality: str
    url: str  # Changed from HttpUrl to str to allow "mp3:" prefix for MP3 conversion
    sizeBytes: int | None = None

class VideoClip(BaseModel):
    id: str
    title: str
    options: list[DownloadOption]
    thumbnailUrl: str | None = None
    durationSeconds: float | None = None
    playlistIndex: int | None = None


class VideoMetadata(VideoClip):
    clips: list[VideoClip]

class URLPayload(BaseModel):
    url: str
    include_mp3: bool = False  # Option to include MP3 conversion

    @field_validator('url')
    @classmethod
    def validate_twitter_url(cls, url: str) -> str:
        return validate_post_url(url)

# --- FastAPI App Setup ---
app = FastAPI(lifespan=lifespan)
app.add_middleware(TrafficMiddleware)

# IMPORTANT: Configure CORS to allow your frontend (running on localhost)
# You must adjust the origin ports if your frontend is not on 5173 or 3000.
origins = [
    "http://localhost:5173",  # Vite default
    "http://localhost:3000",  # Common frontend port
    "http://localhost:3001",  # Vite alternate port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "https://xstream-five.vercel.app",  # Production frontend
    "https://xstream-v1.vercel.app",  # New production domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Core Logic Function ---
def extract_video_metadata(tweet_url: str, include_mp3: bool = False) -> VideoMetadata:
    """Uses yt-dlp to extract the video metadata."""
    
    # Check if yt-dlp is available
    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        raise HTTPException(status_code=503, detail="The downloader is temporarily unavailable. Try again later.")
    
    # yt-dlp command to extract JSON info without downloading the video.
    # The format string prioritizes best quality MP4 video and audio streams.
    # Using a simpler format selector that works better with Twitter/X videos
    command = [
        yt_dlp_path,
        '--ignore-config',
        '--use-extractors', TWITTER_EXTRACTORS,
        '--dump-single-json',
        '--ignore-errors',
        '--skip-download',
        '--no-warnings',
        '--format', 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
        '--',
        tweet_url
    ]
    
    try:
        with subprocess_slot(extraction_slots, "The downloader is busy finding videos. Try again in a few seconds."):
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

        if not result.stdout.strip():
            raise ValueError(
                "Could not load a video from this post. Check that the post is public and contains a video."
            )

        info = json.loads(result.stdout)
        if not isinstance(info, dict):
            raise ValueError("Could not load a video from this post. Check that it is public and contains a video.")
        entries = info.get("entries")
        is_playlist = isinstance(entries, list)
        clips: dict[str, VideoClip] = {}
        for position, entry in enumerate(entries if is_playlist else [info], start=1):
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            index = (entry.get("playlist_index") or position) if is_playlist else None
            clip = build_clip(entry, tweet_url, include_mp3, index)
            if clip.options:
                clips.setdefault(clip.id, clip)

        available = list(clips.values())
        if not available:
            raise ValueError("Could not find downloadable media. Try a different X post.")

        # Older clients read the first result from the original top-level fields.
        return VideoMetadata(**dict(available[0]), clips=available)
    except HTTPException:
        raise
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="X took too long to respond. Please try again.") from e
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="X returned unexpected video information. Try again.") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def build_clip(info: dict, post_url: str, include_mp3: bool, playlist_index: int | None) -> VideoClip:
    formats = (info, *reversed(info.get("formats") or []))
    options_by_height: dict[int, DownloadOption] = {}
    for fmt in formats:
        if (
            fmt.get("ext") != "mp4"
            or fmt.get("protocol") not in (None, "http", "https")
            or fmt.get("vcodec") == "none"
        ):
            continue

        media_url = normalize_allowed_url(fmt.get("url") or "", MEDIA_HOSTS)
        if media_url is None or urlsplit(media_url).path.lower().endswith((".m3u8", ".mpd")):
            continue

        height = fmt.get("height")
        height = height if isinstance(height, int) and height > 0 else 0
        if height not in options_by_height:
            options_by_height[height] = DownloadOption(
                quality=f"{height}p" if height else "Original",
                url=media_url,
                sizeBytes=fmt.get("filesize"),
            )

    options = [options_by_height[height] for height in sorted(options_by_height, reverse=True)]
    has_audio = any(
        fmt.get("acodec") not in (None, "none")
        and normalize_allowed_url(fmt.get("url") or "", MEDIA_HOSTS)
        for fmt in formats
    )
    # Direct MP4s with unknown audio metadata still get a conversion option.
    direct_urls = {option.url for option in options}
    unknown_audio = any(
        fmt.get("acodec") is None and normalize_allowed_url(fmt.get("url") or "", MEDIA_HOSTS) in direct_urls
        for fmt in formats
    )
    if include_mp3 and (has_audio or unknown_audio):
        options.append(DownloadOption(quality="320kbps", url=f"mp3:{post_url}"))

    return VideoClip(
        id=str(info["id"]),
        title=info.get("title") or "Video",
        options=options,
        thumbnailUrl=normalize_allowed_url(info.get("thumbnail") or "", THUMBNAIL_HOSTS),
        durationSeconds=info.get("duration"),
        playlistIndex=playlist_index,
    )


# --- Health Check Route ---
@app.get("/")
@app.get("/health")
async def health_check():
    """Simple health check endpoint for monitoring and keep-alive."""
    return {"status": "ok", "service": "xstream-backend"}


# --- API Route ---
@app.post("/api/video", response_model=VideoMetadata)
def get_video_data(payload: URLPayload):
    """Handles POST request from frontend to fetch video metadata."""
    try:
        return extract_video_metadata(payload.url, include_mp3=payload.include_mp3)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred.") from e


def mp4_attachment(filename: str) -> str:
    stem = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", filename)
    stem = stem.strip(" .")[:120].rstrip(" .") or "video"
    fallback = re.sub(r"[^A-Za-z0-9 ._-]", "_", stem).strip(" ._") or "video"
    encoded = quote(f"{stem}.mp4", safe="")
    return f'attachment; filename="{fallback}.mp4"; filename*=UTF-8\'\'{encoded}'


class MediaUnavailable(HTTPException):
    def __init__(self):
        super().__init__(status_code=502, detail="Could not fetch video from X.")


class ManagedTransfer(StreamingResponse):
    def __init__(self, upstream: httpx.Response, close, deadline: float, headers: dict[str, str]):
        super().__init__(
            self.bounded_body(upstream),
            status_code=upstream.status_code,
            media_type="video/mp4",
            headers=headers,
        )
        self.close_upstream = close
        self.deadline = deadline

    @staticmethod
    async def bounded_body(upstream: httpx.Response):
        sent = 0
        try:
            async for chunk in upstream.aiter_raw():
                sent += len(chunk)
                if sent > MAX_MEDIA_BYTES:
                    raise RuntimeError("Media transfer exceeded the size limit.")
                yield chunk
        except httpx.HTTPError:
            raise RuntimeError("Media transfer interrupted.") from None

    async def __call__(self, scope, receive, send):
        try:
            with anyio.fail_after(max(0, self.deadline - monotonic())):
                await super().__call__(scope, receive, send)
        finally:
            await self.close_upstream()


async def stream_media(
    url: str,
    *,
    download: bool = False,
    filename: str | None = None,
    byte_range: str | None = None,
) -> Response:
    media_url = normalize_allowed_url(url, MEDIA_HOSTS)
    if media_url is None:
        raise HTTPException(status_code=400, detail="Invalid X video URL.")

    if not stream_slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="The downloader is busy transferring files.", headers={"Retry-After": "3"})

    deadline = monotonic() + MEDIA_SECONDS
    client = None
    upstream = None
    handed_off = False

    async def close():
        try:
            with anyio.move_on_after(2, shield=True):
                try:
                    if upstream is not None:
                        await upstream.aclose()
                finally:
                    if client is not None:
                        await client.aclose()
        finally:
            stream_slots.release()

    upstream_headers = {
        "Referer": "https://x.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Encoding": "identity",
    }
    if byte_range and re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", byte_range, re.IGNORECASE):
        upstream_headers["Range"] = byte_range

    try:
        client = httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(10, connect=5))
        with anyio.fail_after(MEDIA_SECONDS):
            upstream = await client.send(client.build_request("GET", media_url, headers=upstream_headers), stream=True)
        content_range = upstream.headers.get("Content-Range")
        if upstream.status_code == 416:
            return Response(status_code=416, headers={"Content-Range": content_range} if content_range else None)
        if upstream.status_code in (401, 403, 404, 410):
            raise MediaUnavailable()
        if upstream.status_code not in (200, 206) or upstream.headers.get("Content-Encoding", "identity") != "identity":
            raise HTTPException(status_code=502, detail="Could not fetch video from X.")

        content_length = upstream.headers.get("Content-Length", "")
        total = content_range.rsplit("/", 1)[-1] if content_range else ""
        for length in (content_length, total):
            if re.fullmatch(r"[0-9]+", length) and int(length) > MAX_MEDIA_BYTES:
                raise HTTPException(status_code=413, detail="This video exceeds the 128 MiB transfer limit.")

        headers = {}
        if re.fullmatch(r"[0-9]+", content_length):
            headers["Content-Length"] = content_length
        for header in ("Accept-Ranges", "Content-Range"):
            if header in upstream.headers:
                headers[header] = upstream.headers[header]
        if download:
            filename = filename or urlsplit(media_url).path.rsplit("/", 1)[-1].removesuffix(".mp4")
            headers["Content-Disposition"] = mp4_attachment(filename)
        else:
            headers["Cache-Control"] = "private, max-age=3600"

        transfer = ManagedTransfer(upstream, close, deadline, headers)
        handed_off = True
        return transfer
    except (httpx.TimeoutException, TimeoutError):
        raise HTTPException(status_code=504, detail="The video transfer timed out. Try again.") from None
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not fetch video from X.") from None
    finally:
        if not handed_off:
            await close()


@app.get("/api/preview")
async def preview_video(url: str, byte_range: Annotated[str | None, Header(alias="Range")] = None):
    return await stream_media(url, byte_range=byte_range)


@app.get("/api/download")
async def download_video(
    request: Request,
    url: str,
    filename: Annotated[str | None, Query(max_length=200)] = None,
    byte_range: Annotated[str | None, Header(alias="Range")] = None,
    post_url: Annotated[str | None, Query(max_length=2048)] = None,
    clip_id: Annotated[str | None, Query(max_length=128)] = None,
    quality: Annotated[str | None, Query(max_length=32)] = None,
    clip_index: Annotated[int | None, Query(ge=1)] = None,
):
    if url.startswith("mp3:"):
        return await convert_for_request(request, url.removeprefix("mp3:"), clip_id=clip_id, clip_index=clip_index)
    if not (post_url and clip_id and quality):
        return await stream_media(url, download=True, filename=filename, byte_range=byte_range)

    error: HTTPException
    try:
        source = require_post_url(post_url)
        try:
            return await stream_media(url, download=True, filename=filename, byte_range=byte_range)
        except MediaUnavailable:
            retry_after = request.state.traffic_budget.retry_after(client_address(request.scope), "extraction", 12)
            if retry_after:
                raise HTTPException(429, "Too many requests. Wait a minute and try again.",
                                    headers={"Retry-After": str(retry_after)})
            metadata = await run_in_threadpool(extract_video_metadata, source)
            clip = next((clip for clip in metadata.clips if clip.id == clip_id), None)
            option = next((option for option in clip.options if option.quality == quality), None) if clip else None
            if option is None:
                raise HTTPException(status_code=409, detail="This clip or quality is no longer available.")
            return await stream_media(option.url, download=True, filename=filename, byte_range=byte_range)
    except HTTPException as e:
        error = e
    except Exception:
        logger.error("MP4 download recovery failed")
        error = HTTPException(status_code=502)

    parameters = {"url": url, "post_url": post_url, "clip_id": clip_id, "quality": quality}
    if filename:
        parameters["filename"] = filename
    return download_error_page(error, parameters)


def download_error_page(error: HTTPException, parameters: dict[str, str]) -> HTMLResponse:
    if error.status_code in (400, 409, 413, 429, 503, 504):
        message = str(error.detail)
    else:
        message = "XStream could not save this MP4. Try the download again in a moment."

    retry = ""
    if error.status_code not in (400, 409, 413):
        retry_url = escape("?" + urlencode(parameters), quote=True)
        retry = f'<p><a href="{retry_url}">Try download again</a></p>'

    return HTMLResponse(
        f"""<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Couldn’t download MP4 · XStream</title>
<main>
<h1>Couldn’t download MP4</h1>
<p>{escape(message)}</p>
{retry}
<p>Go back to XStream to find the post again or choose another format.</p>
</main></html>""",
        status_code=error.status_code,
        headers={"Cache-Control": "no-store", **(error.headers or {})},
    )


# --- MP3 Conversion Function ---
def run_conversion(command: list[str], directory: Path, cancelled: Event):
    # Apply a per-file OS limit separately from the job's aggregate disk budget.
    if os.name == "posix":
        command = [
            sys.executable, "-c",
            "import os, resource, sys\n"
            "size = int(sys.argv[1])\n"
            "resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))\n"
            "os.execv(sys.argv[2], sys.argv[2:])",
            str(MAX_AUDIO_BYTES), *command,
        ]
    deadline = monotonic() + AUDIO_SECONDS
    with subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name == "posix"
    ) as process:
        try:
            while True:
                if cancelled.is_set():
                    raise HTTPException(499, "The download was cancelled.")
                if monotonic() >= deadline:
                    raise HTTPException(504, "The MP3 conversion timed out. Try again.")
                size = 0
                for path in directory.iterdir():
                    try:
                        if path.is_file():
                            size += path.stat().st_size
                    except FileNotFoundError:
                        # yt-dlp can rename a temporary file while it is being counted.
                        continue
                if size > MAX_AUDIO_BYTES:
                    raise HTTPException(413, "This clip exceeds the audio conversion size limit.")
                status = process.poll()
                if status is not None:
                    if status:
                        raise HTTPException(502, "Could not convert this clip to MP3.")
                    return
                cancelled.wait(0.1)
        except BaseException:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                elif process.poll() is None:
                    process.kill()
            except ProcessLookupError:
                pass
            raise


class ConvertedFile(FileResponse):
    def __init__(self, path: Path, directory: Path):
        super().__init__(path, media_type="audio/mpeg", filename="audio.mp3")
        self.directory = directory

    async def __call__(self, scope, receive, send):
        try:
            with anyio.fail_after(MEDIA_SECONDS):
                await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(shutil.rmtree, self.directory, ignore_errors=True)


async def convert_for_request(request: Request, tweet_url: str, **selection):
    cancelled = Event()
    error = None

    async def watch_disconnect():
        try:
            while not await request.is_disconnected():
                await anyio.sleep(0.2)
        finally:
            cancelled.set()

    async with anyio.create_task_group() as group:
        group.start_soon(watch_disconnect)
        try:
            response = await run_in_threadpool(convert_to_mp3, tweet_url, cancelled=cancelled, **selection)
        except Exception as e:
            error = e
        finally:
            group.cancel_scope.cancel()
    if error:
        raise error
    return response


def convert_to_mp3(
    tweet_url: str, *, clip_id: str | None = None, clip_index: int | None = None, cancelled: Event | None = None
):
    """Converts video to MP3 using yt-dlp directly from tweet URL."""
    tweet_url = require_post_url(tweet_url)
    yt_dlp_path = shutil.which("yt-dlp")
    if not yt_dlp_path:
        raise HTTPException(status_code=500, detail="yt-dlp not found")

    cancelled = cancelled if cancelled is not None else Event()
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        command = [
            yt_dlp_path,
            "--ignore-config",
            "--use-extractors", TWITTER_EXTRACTORS,
            "-x", "--audio-format", "mp3", "--audio-quality", "320K",
            "--no-warnings", "--restrict-filenames", "--max-filesize", str(MAX_AUDIO_BYTES),
            "-o", str(tmp_dir / "audio.%(ext)s"),
        ]
        if clip_index is None:
            command.extend(("--no-playlist", "--playlist-items", "1"))
        else:
            command.extend(("--yes-playlist", "--playlist-items", str(clip_index)))
        if clip_id is not None:
            command.extend(("--write-info-json", "--no-write-playlist-metafiles"))
        command.extend(("--", tweet_url))

        with subprocess_slot(conversion_slots, "An audio conversion is already running. Try again in a few seconds."):
            run_conversion(command, tmp_dir, cancelled)

        mp3_path = tmp_dir / "audio.mp3"
        if not mp3_path.is_file():
            raise HTTPException(status_code=502, detail="Could not convert this clip to MP3.")
        if clip_id is not None:
            info_path = tmp_dir / "audio.info.json"
            if not info_path.is_file() or str(json.loads(info_path.read_text())["id"]) != clip_id:
                raise HTTPException(status_code=409, detail="The selected clip has changed. Find the post again.")

        return ConvertedFile(mp3_path, tmp_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


# --- MP3 Conversion Endpoint ---
@app.get("/api/convert-mp3")
async def convert_video_to_mp3(request: Request, tweet_url: str):
    """Converts a Twitter/X video to MP3."""
    return await convert_for_request(request, tweet_url)
