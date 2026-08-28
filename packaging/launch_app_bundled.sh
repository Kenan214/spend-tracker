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
# Floor set by requirements.txt's most demanding dependency (mcp>=2.0 needs
# Python >=3.10) — a venv built with anything older, e.g. the Python 3.9
# stub Xcode Command Line Tools installs at /usr/bin/python3 on Macs with no
# other Python, will "succeed" at venv creation but then fail every install
# of that package with a confusing "from versions: none" pip error.
MIN_PY_MAJOR=3
MIN_PY_MINOR=10

alert() {
  osascript -e "display alert \"Spend Tracker\" message \"$1\" as critical" >/dev/null 2>&1
}

python_new_enough() {
  "$1" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MIN_PY_MAJOR, $MIN_PY_MINOR) else 1)" 2>/dev/null
}

mkdir -p "$SUPPORT_DIR"
export SPEND_TRACKER_DATA_DIR="$SUPPORT_DIR"

# An existing venv from a previous, older/broken interpreter attempt isn't
# good enough just because the directory exists — validate it, or rebuild.
if [ -d "$VENV_DIR" ] && ! python_new_enough "$VENV_DIR/bin/python3"; then
  rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
  osascript -e 'display notification "First launch — setting up, this can take a minute…" with title "Spend Tracker"' >/dev/null 2>&1
  {
    echo "$(date): looking for Python $MIN_PY_MAJOR.$MIN_PY_MINOR+, PATH=$PATH"
  } >>/tmp/spend-tracker.log
  # Try every python3.x on PATH, not just the first one: a broken install
  # (e.g. a Homebrew Python with a broken ensurepip/pyexpat, seen in testing)
  # or one too old for our dependencies shouldn't block launch if a working,
  # sufficiently new interpreter is also available.
  created=0
  for candidate in $(compgen -c python3 | sort -u); do
    command -v "$candidate" >/dev/null 2>&1 || { echo "  $candidate: not runnable" >>/tmp/spend-tracker.log; continue; }
    if ! python_new_enough "$candidate"; then
      echo "  $candidate: $("$candidate" --version 2>&1) — too old or broken" >>/tmp/spend-tracker.log
      continue
    fi
    echo "  $candidate: $("$candidate" --version 2>&1) — trying venv creation" >>/tmp/spend-tracker.log
    rm -rf "$VENV_DIR"
    if "$candidate" -m venv "$VENV_DIR" 2>>/tmp/spend-tracker.log; then
      created=1
      echo "  $candidate: venv created successfully" >>/tmp/spend-tracker.log
      break
    fi
  done
  if [ "$created" -ne 1 ]; then
    rm -rf "$VENV_DIR"
    alert "Couldn't set up Spend Tracker's Python environment — no Python $MIN_PY_MAJOR.$MIN_PY_MINOR+ install was found working. Install Python 3 from python.org, then relaunch Spend Tracker. (Details in /tmp/spend-tracker.log)"
    exit 1
  fi
fi

source "$VENV_DIR/bin/activate"
if ! pip install -q -r "$DIR/requirements.txt" 2>>/tmp/spend-tracker.log; then
  last_error="$(tail -3 /tmp/spend-tracker.log | tr '\n' ' ' | sed 's/"/\\"/g')"
  alert "Couldn't install Spend Tracker's dependencies: ${last_error:-see /tmp/spend-tracker.log for details}"
  exit 1
fi

python "$DIR/src/spend_tracker/desktop_app.py"
