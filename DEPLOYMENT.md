# Deploy XStream

## Backend on Render

The repository-root `render.yaml` defines the Docker web service `xstream-backend-docker`. The image pins Python 3.13.18 and the Python package hashes, installs FFmpeg and FFprobe from Debian Bookworm, and runs as a non-root user. The app refuses to start if a required media tool is missing.

To create the service, use the root Blueprint or create a Docker Web Service linked to this repository. For Dashboard setup, set the root directory to `backend` and leave the Docker start command at its default. Set the health check path to `/health`. The container binds to Render’s `PORT` automatically.

Render service runtimes are immutable. To migrate an existing native Python service, verify the new Docker service before switching Vercel’s API address. The `backend/render.yaml` blueprint remains available for an existing native setup and uses the same Python lock and log-safe start script. The native service needs FFmpeg and FFprobe on its PATH.

The Blueprint uses Render’s **After CI Checks Pass** auto-deploy setting. In Vercel, configure the production branch to require the GitHub regression checks before merging changes.

## Frontend on Vercel

Set `VITE_API_BASE_URL` to the backend origin, for example `https://xstream-backend-docker.onrender.com`. Set it in each Vercel environment that serves the app, then rebuild. For a reverse proxy that serves `/health` and `/api/*` on the frontend origin, set the value to `/`.

The frontend reports a missing or invalid production setting before sending a health request. Device and preview domains that call Render need to be included in the backend’s CORS origins.

## Release checks

Run the local regression suites described in [README.md](./README.md). GitHub Actions also runs the suites, audits npm dependencies, builds the Docker image, and starts it to check readiness.

With Docker installed locally, verify the image with:

```sh
docker build -t xstream-backend backend
docker run --rm -p 127.0.0.1:8000:10000 xstream-backend
```

After deployment, verify `/health`, submit a public X post, seek in the preview, and save both MP4 and MP3. Use a multi-clip post to confirm that the saved files correspond to the selected clip.

## Limits and logging

- Each worker permits two simultaneous extractions, one MP3 conversion, and eight upstream video transfers. Per-client minute budgets are 12 extraction requests, 6 audio requests, and 60 preview or MP4 requests. The counters live in the worker, so multiple workers would need a shared limiter.
- Video transfers are capped at 128 MiB and 90 seconds. MP3 conversion has a 64 MiB temporary-file budget and a 180-second deadline.
- Application request logs contain the route template, status, elapsed time, byte count, and outcome. The Uvicorn entry point disables raw access logs. Review platform-level request-log settings separately.
- The Docker Blueprint uses Render Free. The frontend can wait for the service to wake on the first submission.

To refresh the Python lock deliberately:

```sh
uv pip compile backend/requirements.in --python-version 3.13 --universal --generate-hashes --no-header -o backend/requirements.txt
```
