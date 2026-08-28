#!/bin/bash
# Builds a standalone, distributable "Spend Tracker.app" — with its own copy
# of the source bundled inside Contents/Resources/app/ — and zips it for
# attaching to a GitHub release. Unlike the repo-root dev app, the result
# works when unzipped anywhere, on someone else's Mac, with no repo checkout.
#
# Usage: packaging/build_release.sh <version>   e.g. packaging/build_release.sh v0.1.1
set -euo pipefail

VERSION="${1:?Usage: build_release.sh <version, e.g. v0.1.1>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
APP="$DIST/Spend Tracker.app"

rm -rf "$DIST"
mkdir -p "$DIST"

osacompile -o "$APP" "$ROOT/packaging/launcher_bundled.applescript"

RESOURCES="$APP/Contents/Resources/app"
mkdir -p "$RESOURCES"
cp -R "$ROOT/src" "$RESOURCES/src"
cp "$ROOT/requirements.txt" "$RESOURCES/requirements.txt"
cp "$ROOT/packaging/launch_app_bundled.sh" "$RESOURCES/launch_app.sh"
chmod +x "$RESOURCES/launch_app.sh"

ZIP_NAME="SpendTracker-${VERSION}-macOS.zip"
(cd "$DIST" && zip -rq "$ZIP_NAME" "Spend Tracker.app")

echo "Built $DIST/$ZIP_NAME"
