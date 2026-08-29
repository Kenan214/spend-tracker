# Builds a standalone, distributable Windows release -- a folder holding
# SpendTracker.bat + launcher.ps1 (see packaging/launcher.bat and
# packaging/launcher.ps1 for what those do on double-click) plus its own
# copy of the source under app/ -- and zips it for attaching to a GitHub
# release. Unlike the repo-root dev checkout, the result works when
# unzipped anywhere, on someone else's Windows machine, with no repo
# checkout and no dependency on this machine's PATH.
#
# Usage: packaging/build_release.ps1 <version>   e.g. packaging/build_release.ps1 v0.1.1
param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dist = Join-Path $Root "dist"
# Staged under a "Spend Tracker" folder (not directly in dist/) so the zip
# extracts to a single named folder rather than dumping loose files into
# wherever the user unzips it -- mirrors macOS's --keepParent behavior for
# "Spend Tracker.app".
$StageDir = Join-Path $Dist "Spend Tracker"
$AppDir = Join-Path $StageDir "app"

if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

Copy-Item (Join-Path $Root "packaging\launcher.bat") (Join-Path $StageDir "SpendTracker.bat")
Copy-Item (Join-Path $Root "packaging\launcher.ps1") (Join-Path $StageDir "launcher.ps1")

Copy-Item -Recurse (Join-Path $Root "src") (Join-Path $AppDir "src")
Copy-Item (Join-Path $Root "requirements.txt") (Join-Path $AppDir "requirements.txt")

# __pycache__ picked up from a local dev run under src/ shouldn't ship --
# it's stale bytecode tied to whatever interpreter last ran it here, not
# the venv the launcher creates on the machine it's unzipped on.
Get-ChildItem -Path $AppDir -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

# The (future) updater's source of truth for "what version is this install"
# -- kept as the exact tag (e.g. "v0.1.2"), matching macOS: compared
# directly against GitHub release tag_names, no v-stripping/reformatting.
Set-Content -Path (Join-Path $AppDir "VERSION") -Value $Version -NoNewline -Encoding utf8

$ZipName = "SpendTracker-$Version-Windows.zip"
$ZipPath = Join-Path $Dist $ZipName
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $StageDir -DestinationPath $ZipPath

Write-Host "Built $ZipPath"
