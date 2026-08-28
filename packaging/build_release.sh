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

# Built in a scratch dir outside the repo, not under $DIST: if the repo sits
# under an iCloud-synced folder (e.g. ~/Desktop), the File Provider daemon
# keeps re-attaching xattrs (com.apple.FinderInfo etc.) to files there in
# the background, racing with codesign and re-triggering the "resource
# fork... detritus not allowed" failure right after it's been cleared.
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
APP="$SCRATCH/Spend Tracker.app"

rm -rf "$DIST"
mkdir -p "$DIST"

osacompile -o "$APP" "$ROOT/packaging/launcher_bundled.applescript"

RESOURCES="$APP/Contents/Resources/app"
mkdir -p "$RESOURCES"
cp -R "$ROOT/src" "$RESOURCES/src"
cp "$ROOT/requirements.txt" "$RESOURCES/requirements.txt"
cp "$ROOT/packaging/launch_app_bundled.sh" "$RESOURCES/launch_app.sh"
chmod +x "$RESOURCES/launch_app.sh"

# __pycache__ (stale bytecode from running src/ locally) and any extended
# attributes carried over by cp (e.g. com.apple.provenance) both make
# `codesign --verify --strict` refuse the bundle as containing "detritus".
find "$RESOURCES" -name "__pycache__" -type d -exec rm -rf {} +
xattr -cr "$APP"

# osacompile ad-hoc signs and seals the bundle's resources at creation time;
# adding files into Contents/Resources afterward invalidates that seal,
# which macOS reports to users as "<app> is damaged and can't be opened" —
# not the friendlier "unidentified developer" prompt. Re-sign after adding
# our files so the seal covers everything actually in the bundle.
codesign --force --deep --sign - "$APP"
# "code failed to satisfy specified code requirement(s)" / rejected here is
# expected — this is an ad-hoc signature, not a notarized Developer ID one,
# so Gatekeeper will still show its normal "unidentified developer" prompt.
# What this check actually guards against is "damaged" (a torn seal) or a
# reported-missing binary, either of which would show up as a different
# error string below.
spctl -a -vvv "$APP" || true
codesign --verify --deep --strict "$APP"

# `zip -r` is known to corrupt app bundle signatures/resource forks; Apple's
# own recommended tool for zipping .app bundles for distribution is ditto.
ZIP_NAME="SpendTracker-${VERSION}-macOS.zip"
(cd "$SCRATCH" && ditto -c -k --keepParent "Spend Tracker.app" "$DIST/$ZIP_NAME")
cp -R "$APP" "$DIST/Spend Tracker.app"

echo "Built $DIST/$ZIP_NAME"
