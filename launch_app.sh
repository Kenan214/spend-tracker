#!/bin/bash
# Sets up the venv if needed and launches the native Spend Tracker window.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

python src/spend_tracker/desktop_app.py
