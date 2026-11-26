FROM python:3.13.18-slim-bookworm@sha256:f0fa218d5b06f9b9235024fa061cde2cb141f726de52134471053d2d9b5324a3

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt \
    && ffmpeg -version >/dev/null \
    && ffprobe -version >/dev/null \
    && yt-dlp --version

COPY main.py start.sh ./
USER 10001:10001
CMD ["sh", "start.sh"]
