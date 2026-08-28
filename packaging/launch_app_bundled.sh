#!/bin/bash
# Copied into Contents/Resources/app/launch_app.sh by build_release.sh.
#
# Keeps the venv and user data in ~/Library/Application Support instead of
# inside the .app bundle: the bundle may be running from a read-only,
# Gatekeeper-translocated location (macOS runs quarantined, unmoved .app
# bundles from a randomized read-only mount), so nothing here can rely on
# being able to write next to itself, or on paths outside the bundle being
# visible at all.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUPPORT_DIR="$HOME/Library/Application Support/Spend Tracker"
VENV_DIR="$SUPPORT_DIR/venv"

alert() {
  osascript -e "display alert \"Spend Tracker\" message \"$1\" as critical" >/dev/null 2>&1
}

mkdir -p "$SUPPORT_DIR"
export SPEND_TRACKER_DATA_DIR="$SUPPORT_DIR"

if [ ! -d "$VENV_DIR" ]; then
  osascript -e 'display notification "First launch — setting up, this can take a minute…" with title "Spend Tracker"' >/dev/null 2>&1
  # Try every python3.x on PATH, not just the first one: a broken install
  # (e.g. a Homebrew Python with a broken ensurepip/pyexpat, seen in testing)
  # shouldn't block launch if a working interpreter is also available.
  created=0
  for candidate in $(compgen -c python3 | sort -u); do
    command -v "$candidate" >/dev/null 2>&1 || continue
    rm -rf "$VENV_DIR"
    if "$candidate" -m venv "$VENV_DIR" 2>>/tmp/spend-tracker.log; then
      created=1
      break
    fi
  done
  if [ "$created" -ne 1 ]; then
    rm -rf "$VENV_DIR"
    alert "Couldn't set up Spend Tracker's Python environment — no working Python 3 install was found. Install Python 3 from python.org, then relaunch Spend Tracker. (Details in /tmp/spend-tracker.log)"
    exit 1
  fi
fi

source "$VENV_DIR/bin/activate"
if ! pip install -q -r "$DIR/requirements.txt"; then
  alert "Couldn't install Spend Tracker's dependencies. Check your internet connection and try again."
  exit 1
fi

python "$DIR/src/spend_tracker/desktop_app.py"
