#!/usr/bin/env bash
# Run inside Ubuntu 24.04 after installing PX4/Gazebo system dependencies.
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$HOME/llm-drone-demo-runtime"
mkdir -p "$RUNTIME_DIR/app"
if [[ "$SOURCE_DIR" != "$RUNTIME_DIR/app" ]]; then
  rsync -a --exclude=.venv --exclude=logs --exclude='*.mp4' "$SOURCE_DIR/" "$RUNTIME_DIR/app/"
fi
python3 -m venv "$RUNTIME_DIR/.venv"
"$RUNTIME_DIR/.venv/bin/pip" install -r "$RUNTIME_DIR/app/requirements.txt"
"$RUNTIME_DIR/.venv/bin/pip" install playwright==1.55.0
"$RUNTIME_DIR/.venv/bin/playwright" install chromium
ollama pull qwen2.5:1.5b
chmod +x "$RUNTIME_DIR/app/scripts/"*.sh
