#!/bin/sh
# Run the agent locally with auto-reload. Requires .env (copy from .env.example)
# and gcloud ADC (gcloud auth application-default login).
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "No .env found - copy .env.example to .env and set GOOGLE_CLOUD_PROJECT" >&2
    exit 1
fi

exec .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port "${PORT:-8080}"
