#!/usr/bin/env bash
set -euo pipefail
RUNTIME_DIR="$HOME/llm-drone-demo-runtime"
source "$RUNTIME_DIR/.venv/bin/activate"
cd "$RUNTIME_DIR/app"
exec python app.py
