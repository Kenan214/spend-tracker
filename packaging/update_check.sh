#!/bin/bash
# Self-updater: checks GitHub Releases for a newer version and, if found,
# downloads + stages it under Application Support for the *next* launch to
# swap in (see the "apply pending update" block at the top of ../MacOS/
# launcher). Spawned detached, in the background, by the launcher on every
# run — never blocks app startup, and every step below is best-effort: any
# failure just leaves the current install running untouched. No dialogs,
# no alerts, no exit codes anyone checks.
#
# The trick this relies on: the com.apple.quarantine xattr that triggers
# Gatekeeper's "unidentified developer" block is only attached by
# quarantine-aware tools (Safari, Mail, Finder's unzip-from-download). A
# plain `curl` download run by this already-approved, already-running app
# does NOT get it — so a release fetched this way and swapped into place
# launches clean next time, no re-approval needed. Same trick Sparkle and
# other third-party Mac auto-updaters use.
set -u

CURRENT_VERSION="${1:-v0.0.0}"
REPO="Kenan214/spend-tracker"
SUPPORT_DIR="$HOME/Library/Application Support/Spend Tracker"
PENDING_DIR="$SUPPORT_DIR/pending_update"
LOG="/tmp/spend-tracker-updater.log"
THROTTLE_FILE="$SUPPORT_DIR/last_update_check"
THROTTLE_SECONDS=1800 # don't hit the GitHub API more than every 30 min

log() { echo "$(date): $*" >>"$LOG"; }

# Compares dotted version numbers numerically (so v0.2.0 > v0.10.0 is
# judged correctly, unlike a plain string compare) without depending on
# GNU `sort -V`, which macOS's built-in BSD sort doesn't have.
version_gt() {
  local v1="${1#v}" v2="${2#v}"
  local IFS=.
  local -a a=($v1) b=($v2)
  local i x y
  for i in 0 1 2; do
    x="${a[i]:-0}"; y="${b[i]:-0}"
    [[ "$x" =~ ^[0-9]+$ ]] || x=0
    [[ "$y" =~ ^[0-9]+$ ]] || y=0
    if ((10#$x > 10#$y)); then return 0; fi
    if ((10#$x < 10#$y)); then return 1; fi
  done
  return 1
}

mkdir -p "$SUPPORT_DIR"

now="$(date +%s)"
if [ -f "$THROTTLE_FILE" ]; then
  last="$(cat "$THROTTLE_FILE" 2>/dev/null || echo 0)"
  [[ "$last" =~ ^[0-9]+$ ]] || last=0
  if (( now - last < THROTTLE_SECONDS )); then
    log "skipping check, last checked ${last}s ago"
    exit 0
  fi
fi
echo "$now" >"$THROTTLE_FILE"

# Already have a verified, still-newer update staged from a previous
# launch's check — nothing to do, it'll be applied next launch.
if [ -f "$PENDING_DIR/READY" ] && [ -f "$PENDING_DIR/VERSION" ]; then
  staged="$(cat "$PENDING_DIR/VERSION" 2>/dev/null)"
  if [ -n "$staged" ] && version_gt "$staged" "$CURRENT_VERSION"; then
    log "already have $staged staged, skipping"
    exit 0
  fi
fi

api_response="$(curl -fsSL --connect-timeout 5 --max-time 15 \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases/latest" 2>>"$LOG")" || {
  log "GitHub API fetch failed"
  exit 0
}

latest_tag="$(printf '%s' "$api_response" | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')"
if [ -z "$latest_tag" ]; then
  log "couldn't parse tag_name from API response"
  exit 0
fi

if ! version_gt "$latest_tag" "$CURRENT_VERSION"; then
  log "up to date (running $CURRENT_VERSION, latest is $latest_tag)"
  exit 0
fi

asset_url="$(printf '%s' "$api_response" \
  | grep -o '"browser_download_url": *"[^"]*SpendTracker-[^"]*-macOS\.zip"' \
  | sed -E 's/.*"(https:[^"]+)"/\1/' | head -1)"
if [ -z "$asset_url" ]; then
  log "release $latest_tag has no SpendTracker-*-macOS.zip asset"
  exit 0
fi

log "newer version available: $latest_tag (currently $CURRENT_VERSION), downloading from $asset_url"
DL_DIR="$(mktemp -d /tmp/spend-tracker-update.XXXXXX)"
if [ -z "$DL_DIR" ] || [ ! -d "$DL_DIR" ]; then
  log "mktemp failed, aborting"
  exit 0
fi
trap 'rm -rf "$DL_DIR"' EXIT
ZIP_PATH="$DL_DIR/update.zip"

if ! curl -fsSL --connect-timeout 5 --max-time 180 -o "$ZIP_PATH" "$asset_url" 2>>"$LOG"; then
  log "download failed"
  exit 0
fi

# This is the load-bearing assumption of the whole feature — verify it,
# don't just trust it. A plain curl download shouldn't get tagged, but
# strip defensively either way; it costs nothing and it's cheap insurance
# against some future environment (proxy, corporate MDM, etc.) behaving
# differently.
if xattr -p com.apple.quarantine "$ZIP_PATH" >/dev/null 2>&1; then
  log "WARNING: downloaded zip unexpectedly carries com.apple.quarantine"
fi
xattr -cr "$ZIP_PATH" 2>/dev/null || true

if ! ditto -x -k "$ZIP_PATH" "$DL_DIR" 2>>"$LOG"; then
  log "extraction failed"
  exit 0
fi

NEW_APP="$DL_DIR/Spend Tracker.app"
if [ ! -d "$NEW_APP" ]; then
  log "extracted zip has no 'Spend Tracker.app'"
  exit 0
fi

xattr -cr "$NEW_APP" 2>/dev/null || true
if ! codesign --verify --deep --strict "$NEW_APP" 2>>"$LOG"; then
  log "downloaded app failed codesign verification, discarding"
  exit 0
fi

new_version="$(cat "$NEW_APP/Contents/Resources/app/VERSION" 2>/dev/null)"
[ -n "$new_version" ] || new_version="$latest_tag"

# Only now — everything downloaded, extracted, and verified — touch the
# real staging dir the launcher looks at, and only mark it READY last, so
# a half-finished check (killed mid-run, disk full, etc.) never leaves a
# half-staged update for the launcher to swap in.
rm -rf "$PENDING_DIR"
mkdir -p "$PENDING_DIR"
mv "$NEW_APP" "$PENDING_DIR/Spend Tracker.app"
echo "$new_version" >"$PENDING_DIR/VERSION"
touch "$PENDING_DIR/READY"
log "staged $new_version, will apply on next launch"
