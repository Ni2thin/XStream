import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from starlette.background import BackgroundTask

POST_HOSTS = frozenset(
    f"{prefix}{domain}"
    for domain in ("x.com", "twitter.com")
    for prefix in ("", "www.", "m.", "mobile.")
)
MEDIA_HOSTS = frozenset({"video.twimg.com", "pbs.twimg.com"})
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

class VideoMetadata(BaseModel):
    id: str
    title: str
    options: list[DownloadOption]

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
        
        options_map: dict[str, DownloadOption] = {}
        
        # First, try to get the direct URL from the selected format
        best_url = normalize_allowed_url(info.get('url') or '', MEDIA_HOSTS)
        if best_url and info.get('ext') == 'mp4':
            height = info.get('height') or info.get('format_note', '').replace('p', '')
            if height:
                try:
                    height_int = int(str(height).replace('p', ''))
                    if height_int >= 360:
                        quality = f"{height_int}p"
                        options_map[quality] = DownloadOption(quality=quality, url=best_url)
                except (ValueError, AttributeError):
                    pass
        
        # Also iterate through all formats to find direct MP4 download links
        for fmt in info.get('formats', []):
            fmt_ext = fmt.get('ext', '').lower()
            fmt_url = normalize_allowed_url(fmt.get('url') or '', MEDIA_HOSTS)
            
            if fmt_ext == 'mp4' and fmt_url:
                height = fmt.get('height')
                
                if height and height >= 360:  # Filter out very low-res or non-video streams
                    quality = f"{height}p"
                    
                    # Store only the highest quality found for a given resolution level
                    if quality not in options_map:
                        options_map[quality] = DownloadOption(quality=quality, url=fmt_url)
        
        final_options = list(options_map.values())
        
        # If no suitable options are found, try to use the best available format
        if not final_options:
            # Fallback: use the best format available, even if not MP4
            if best_url:
                height = info.get('height') or 720
                quality = f"{height}p" if height else "best"
                final_options = [DownloadOption(quality=quality, url=best_url)]
            else:
                raise ValueError("Could not find suitable download links. Video may be private, deleted, or embedded differently.")

        # Sort options from highest to lowest quality (only sort video options)
        video_options = [opt for opt in final_options if not opt.url.startswith('mp3:')]
        mp3_options = [opt for opt in final_options if opt.url.startswith('mp3:')]
        
        video_options.sort(key=lambda x: int(x.quality.replace('p', '')) if x.quality.replace('p', '').isdigit() else 0, reverse=True)
        
        # Add MP3 option if requested (add it at the end, after video options)
        if include_mp3:
            # Store the tweet URL for MP3 conversion
            mp3_option = DownloadOption(quality="320kbps", url=f"mp3:{tweet_url}")
            mp3_options.append(mp3_option)
            print(f"DEBUG: Added MP3 option with URL: mp3:{tweet_url}")  # Debug log
        
        # Combine video and MP3 options
        final_options = video_options + mp3_options
        print(f"DEBUG: Final options count: {len(final_options)}, MP3 count: {len(mp3_options)}")  # Debug log
        
        return VideoMetadata(
            id=video_id,
            title=title,
            options=final_options
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


def stream_media(url: str, *, download: bool = False) -> StreamingResponse:
    media_url = normalize_allowed_url(url, MEDIA_HOSTS)
    if media_url is None:
        raise HTTPException(status_code=400, detail="Invalid X video URL.")

    try:
        response = requests.get(
            media_url,
            stream=True,
            timeout=30,
            # Only contact the validated CDN origin.
            allow_redirects=False,
            headers={
                "Referer": "https://x.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Encoding": "identity",
            },
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="Could not fetch video from X.") from e

    if response.status_code != 200:
        response.close()
        raise HTTPException(status_code=502, detail="Could not fetch video from X.")

    headers = {}
    content_length = response.headers.get("Content-Length")
    if content_length and not response.headers.get("Content-Encoding"):
        headers["Content-Length"] = content_length
    if download:
        filename = urlsplit(media_url).path.rsplit("/", 1)[-1] or "video.mp4"
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        headers["Cache-Control"] = "public, max-age=3600"

    return StreamingResponse(
        response.iter_content(chunk_size=8192),
        media_type="video/mp4",
        headers=headers,
        background=BackgroundTask(response.close),
    )


@app.get("/api/preview")
def preview_video(url: str):
    return stream_media(url)


@app.get("/api/download")
def download_video(url: str):
    if url.startswith("mp3:"):
        return convert_to_mp3(url.removeprefix("mp3:"))
    return stream_media(url, download=True)


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
