#!/bin/zsh
set -e
DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEMO_DIR"
export BOXLITE_DEMO_STATE_DIR="${BOXLITE_DEMO_STATE_DIR:-$HOME/Library/Application Support/BoxLiteDemo}"
mkdir -p "$BOXLITE_DEMO_STATE_DIR"
chmod 700 "$BOXLITE_DEMO_STATE_DIR"
DEMO_PY="$BOXLITE_DEMO_STATE_DIR/venv/bin/python"
if [ ! -x "$DEMO_PY" ]; then
  python3 -m venv "$BOXLITE_DEMO_STATE_DIR/venv"
fi
if ! "$DEMO_PY" -c "import boxlite" >/dev/null 2>&1; then
  "$DEMO_PY" -m pip install -r requirements.txt
fi
exec "$DEMO_PY" -u work/boxlite-connect/local_demo.py
