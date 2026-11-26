#!/bin/sh
set -eu
exec python -m uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-10000}" --no-access-log --no-proxy-headers
