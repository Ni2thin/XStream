from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, HttpUrl, validator
import json
import subprocess
import shlex
import shutil  # Used for checking if yt-dlp is available
import tempfile
import os
import requests
from urllib.parse import urlparse

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

    # Optional: Basic validation to check if the URL looks like an X/Twitter link
    @validator('url')
    def validate_twitter_url(cls, v):
        if not (v.startswith('http') and ('x.com' in v or 'twitter.com' in v)):
            raise ValueError('URL must be a valid X/Twitter link.')
        return v

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
        '--dump-json',
        '--skip-download',
        '--no-warnings',
        '--format', 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
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
        if info.get('url') and info.get('ext') == 'mp4':
            height = info.get('height') or info.get('format_note', '').replace('p', '')
            if height:
                try:
                    height_int = int(str(height).replace('p', ''))
                    if height_int >= 360:
                        quality = f"{height_int}p"
                        options_map[quality] = DownloadOption(quality=quality, url=info['url'])
                except (ValueError, AttributeError):
                    pass
        
        # Also iterate through all formats to find direct MP4 download links
        for fmt in info.get('formats', []):
            fmt_ext = fmt.get('ext', '').lower()
            fmt_url = fmt.get('url')
            
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
            best_url = info.get('url')
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
        # Handle errors reported by yt-dlp (e.g., video not found, Geo-restriction)
        error_output = e.stderr.strip() if e.stderr else e.stdout.strip() if e.stdout else "Unknown yt-dlp error."
        raise HTTPException(status_code=400, detail=f"Extraction failed: {error_output}")
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


# --- Preview Proxy Route ---
@app.get("/api/preview")
async def preview_video(url: str):
    """Proxies video for preview to handle CORS restrictions."""
    try:
        # Validate that the URL is from Twitter/X video domain
        parsed_url = urlparse(url)
        if 'video.twimg.com' not in parsed_url.netloc and 'twimg.com' not in parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Invalid video URL")
        
        # Stream the video from Twitter with proper headers
        headers = {
            'Referer': 'https://x.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status()
        
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="video/mp4",
            headers={
                "Content-Type": "video/mp4",
                "Accept-Ranges": "bytes",
                "Content-Length": str(response.headers.get('content-length', '')),
                "Cache-Control": "public, max-age=3600",
            }
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to load video: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# --- Download Proxy Route ---
@app.get("/api/download")
async def download_video(url: str):
    """Proxies video download to handle CORS restrictions."""
    try:
        # Check if this is an MP3 conversion request
        if url.startswith("mp3:"):
            # Extract the tweet URL
            tweet_url = url[4:]  # Remove "mp3:" prefix
            return await convert_to_mp3(tweet_url)
        
        # Validate that the URL is from Twitter/X video domain
        parsed_url = urlparse(url)
        if 'video.twimg.com' not in parsed_url.netloc and 'twimg.com' not in parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Invalid video URL")
        
        # Stream the video from Twitter with proper headers
        headers = {
            'Referer': 'https://x.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Get filename from URL or use default
        filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
        
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(response.headers.get('content-length', '')),
            }
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to download video: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# --- MP3 Conversion Function ---
async def convert_to_mp3(tweet_url: str):
    """Converts video to MP3 using yt-dlp directly from tweet URL."""
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
                '-x',  # Extract audio only
                '--audio-format', 'mp3',
                '--audio-quality', '320K',  # High quality audio
                '--no-warnings',
                '--no-playlist',
                '--restrict-filenames',
                '-o', output_template,
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
async def convert_video_to_mp3(tweet_url: str):
    """Converts a Twitter/X video to MP3."""
    try:
        # Validate tweet URL
        if not (tweet_url.startswith('http') and ('x.com' in tweet_url or 'twitter.com' in tweet_url)):
            raise HTTPException(status_code=400, detail="Invalid tweet URL")
        
        return await convert_to_mp3(tweet_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")