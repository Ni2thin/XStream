import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Annotated
from urllib.parse import quote, urlsplit

import requests
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, validator
from starlette.background import BackgroundTask

POST_HOSTS = frozenset(
    f"{prefix}{domain}"
    for domain in ("x.com", "twitter.com")
    for prefix in ("", "www.", "m.", "mobile.")
)
THUMBNAIL_HOSTS = frozenset({"pbs.twimg.com"})
MEDIA_HOSTS = THUMBNAIL_HOSTS | {"video.twimg.com"}
TWITTER_EXTRACTORS = "twitter,twitter:card,twitter:amplify,twitter:broadcast,twitter:spaces"


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

# --- Pydantic Models for API ---
# These models define the expected input and output JSON structure.
class DownloadOption(BaseModel):
    quality: str
    url: str  # Changed from HttpUrl to str to allow "mp3:" prefix for MP3 conversion
    sizeBytes: int | None = None

class VideoMetadata(BaseModel):
    id: str
    title: str
    options: list[DownloadOption]
    thumbnailUrl: str | None = None
    durationSeconds: float | None = None

class URLPayload(BaseModel):
    url: str
    include_mp3: bool = False  # Option to include MP3 conversion

    @validator('url')
    def validate_twitter_url(cls, url: str) -> str:
        return validate_post_url(url)

# --- FastAPI App Setup ---
app = FastAPI()

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
        raise EnvironmentError("yt-dlp executable not found. Please ensure it is installed and in your PATH.")
    
    # yt-dlp command to extract JSON info without downloading the video.
    # The format string prioritizes best quality MP4 video and audio streams.
    # Using a simpler format selector that works better with Twitter/X videos
    command = [
        yt_dlp_path,
        '--ignore-config',
        '--use-extractors', TWITTER_EXTRACTORS,
        '--dump-json',
        '--skip-download',
        '--no-warnings',
        '--format', 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
        '--',
        tweet_url
    ]
    
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30  # Increased timeout for slower connections
        )
        
        if not result.stdout.strip():
            raise ValueError("yt-dlp returned empty output. The video may not be accessible.")
        
        info = json.loads(result.stdout)
        
        title = info.get('title', 'Video')
        video_id = info.get('id', 'unknown_id')
        
        formats = (info, *reversed(info.get("formats") or []))
        options_by_height: dict[int, DownloadOption] = {}
        # The download proxy serves complete MP4 files. A streaming manifest is not an MP4 file.
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
        if include_mp3:
            # Posts without a direct MP4 can still have an audio stream that yt-dlp can convert.
            if options or any(
                fmt.get("acodec") not in (None, "none")
                and normalize_allowed_url(fmt.get("url") or "", MEDIA_HOSTS)
                for fmt in formats
            ):
                options.append(DownloadOption(quality="320kbps", url=f"mp3:{tweet_url}"))
        if not options:
            raise ValueError("Could not find downloadable media. Try a different X post.")
        
        return VideoMetadata(
            id=video_id,
            title=title,
            options=options,
            thumbnailUrl=normalize_allowed_url(info.get("thumbnail") or "", THUMBNAIL_HOSTS),
            durationSeconds=info.get("duration"),
        )

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=400,
            detail="Could not load a video from this post. Check that the post is public and contains a video, then try again.",
        ) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="X took too long to respond. Please try again.") from e
    except json.JSONDecodeError as e:
        # Handle JSON parsing errors
        raise HTTPException(status_code=500, detail=f"Failed to parse yt-dlp output: {str(e)}")
    except EnvironmentError as e:
        # Handle missing yt-dlp executable
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        # Handle value errors (no formats found, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle parsing or other general errors
        raise HTTPException(status_code=500, detail=f"Internal server error during processing: {str(e)}")


# --- Health Check Route ---
@app.get("/")
@app.get("/health")
async def health_check():
    """Simple health check endpoint for monitoring and keep-alive."""
    return {"status": "ok", "service": "xstream-backend"}


# --- API Route ---
@app.post("/api/video", response_model=VideoMetadata)
async def get_video_data(payload: URLPayload):
    """Handles POST request from frontend to fetch video metadata."""
    try:
        print(f"DEBUG: Received request with include_mp3={payload.include_mp3}")  # Debug log
        metadata = extract_video_metadata(payload.url, include_mp3=payload.include_mp3)
        print(f"DEBUG: Returning {len(metadata.options)} options")  # Debug log
        return metadata
    except HTTPException as e:
        # Re-raise explicit HTTP errors (400, 500)
        raise e
    except Exception:
        # Catch remaining uncaught exceptions
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


def mp4_attachment(filename: str) -> str:
    stem = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', "_", filename)
    stem = stem.strip(" .")[:120].rstrip(" .") or "video"
    fallback = re.sub(r"[^A-Za-z0-9 ._-]", "_", stem).strip(" ._") or "video"
    encoded = quote(f"{stem}.mp4", safe="")
    return f'attachment; filename="{fallback}.mp4"; filename*=UTF-8\'\'{encoded}'


def stream_media(
    url: str,
    *,
    download: bool = False,
    filename: str | None = None,
    byte_range: str | None = None,
) -> Response:
    media_url = normalize_allowed_url(url, MEDIA_HOSTS)
    if media_url is None:
        raise HTTPException(status_code=400, detail="Invalid X video URL.")

    upstream_headers = {
        "Referer": "https://x.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Encoding": "identity",
    }
    if byte_range and re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", byte_range, re.IGNORECASE):
        upstream_headers["Range"] = byte_range

    try:
        response = requests.get(
            media_url,
            stream=True,
            timeout=30,
            # Only contact the validated CDN origin.
            allow_redirects=False,
            headers=upstream_headers,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="Could not fetch video from X.") from e

    if response.status_code == 416:
        content_range = response.headers.get("Content-Range")
        response.close()
        return Response(status_code=416, headers={"Content-Range": content_range} if content_range else None)

    if response.status_code not in (200, 206):
        response.close()
        raise HTTPException(status_code=502, detail="Could not fetch video from X.")

    headers = {}
    content_length = response.headers.get("Content-Length")
    if content_length and not response.headers.get("Content-Encoding"):
        headers["Content-Length"] = content_length
    for header in ("Accept-Ranges", "Content-Range"):
        if header in response.headers:
            headers[header] = response.headers[header]
    if download:
        filename = filename or urlsplit(media_url).path.rsplit("/", 1)[-1].removesuffix(".mp4")
        headers["Content-Disposition"] = mp4_attachment(filename)
    else:
        headers["Cache-Control"] = "public, max-age=3600"

    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        status_code=response.status_code,
        media_type="video/mp4",
        headers=headers,
        background=BackgroundTask(response.close),
    )


@app.get("/api/preview")
def preview_video(url: str, byte_range: Annotated[str | None, Header(alias="Range")] = None):
    return stream_media(url, byte_range=byte_range)


@app.get("/api/download")
def download_video(
    url: str,
    filename: Annotated[str | None, Query(max_length=200)] = None,
    byte_range: Annotated[str | None, Header(alias="Range")] = None,
):
    if url.startswith("mp3:"):
        return convert_to_mp3(url.removeprefix("mp3:"))
    return stream_media(url, download=True, filename=filename, byte_range=byte_range)


# --- MP3 Conversion Function ---
def convert_to_mp3(tweet_url: str):
    """Converts video to MP3 using yt-dlp directly from tweet URL."""
    try:
        tweet_url = validate_post_url(tweet_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        yt_dlp_path = shutil.which('yt-dlp')
        if not yt_dlp_path:
            raise HTTPException(status_code=500, detail="yt-dlp not found")
        
        tmp_dir = tempfile.mkdtemp()
        output_template = os.path.join(tmp_dir, "audio.%(ext)s")
        
        try:
            # Use yt-dlp to extract audio directly from tweet URL and convert to MP3
            command = [
                yt_dlp_path,
                '--ignore-config',
                '--use-extractors', TWITTER_EXTRACTORS,
                '-x',  # Extract audio only
                '--audio-format', 'mp3',
                '--audio-quality', '320K',  # High quality audio
                '--no-warnings',
                '--no-playlist',
                '--restrict-filenames',
                '-o', output_template,
                '--',
                tweet_url
            ]
            
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=180  # allow extra time for conversion
            )
            
            # Find the generated MP3 file
            mp3_files = [f for f in os.listdir(tmp_dir) if f.endswith('.mp3')]
            if not mp3_files:
                raise HTTPException(status_code=500, detail="MP3 conversion failed: file not created")
            
            mp3_path = os.path.join(tmp_dir, mp3_files[0])
            filename = mp3_files[0]
            
            def generate():
                with open(mp3_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        yield chunk
            
            def cleanup():
                try:
                    shutil.rmtree(tmp_dir)
                except Exception:
                    pass
            
            return StreamingResponse(
                generate(),
                media_type="audio/mpeg",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
                background=BackgroundTask(cleanup)
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            error_msg = e.stderr.strip() if e.stderr else e.stdout.strip() if e.stdout else "Unknown error"
            raise HTTPException(status_code=500, detail=f"MP3 conversion failed: {error_msg}")
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MP3 conversion error: {str(e)}")


# --- MP3 Conversion Endpoint ---
@app.get("/api/convert-mp3")
def convert_video_to_mp3(tweet_url: str):
    """Converts a Twitter/X video to MP3."""
    return convert_to_mp3(tweet_url)
