#!/bin/bash
# Start the Myanmar Dub web app at http://localhost:8000
cd "$(dirname "$0")"
source .venv/bin/activate
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
