# Windows counterpart to packaging/launcher (macOS) -- the script behind
# SpendTracker.bat, run on double-click. Locates or bootstraps a Python
# 3.10+ venv, points the app at a writable per-user data dir, and launches
# desktop_app.py.
#
# Self-update (the "apply a staged update" block the macOS launcher has at
# the top) lands in a later change alongside the Windows update_check
# script -- this is bootstrap+launch only, matching that task split.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $ScriptDir "app"
# Mirrors the macOS launcher's use of ~/Library/Application Support: a
# per-user, always-writable location outside the installed app folder, so
# the venv and user data survive replacing this folder with a newer build
# and don't depend on write access to wherever the app happens to be
# unzipped (e.g. Program Files, which standard users can't write to).
$SupportDir = Join-Path $env:LOCALAPPDATA "Spend Tracker"
$VenvDir = Join-Path $SupportDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$LogFile = Join-Path $env:TEMP "spend-tracker.log"
$MinPyMajor = 3
$MinPyMinor = 10

# Last-resort safety net: this script must never fail silently with just a
# console window flashing shut, since a double-clicked app has no other way
# to tell the user something went wrong.
trap {
    Write-Log "unhandled error: $_"
    Show-Alert "Spend Tracker hit an unexpected error during startup: $_`n`n(Details in $LogFile)"
    exit 1
}

function Write-Log([string]$Message) {
    "$(Get-Date): $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Show-Alert([string]$Message) {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show($Message, "Spend Tracker", "OK", "Error") | Out-Null
}

function Test-PythonNewEnough([string]$PythonExe, [string[]]$PreArgs = @()) {
    & $PythonExe @PreArgs -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MinPyMajor, $MinPyMinor) else 1)" *> $null
    return $LASTEXITCODE -eq 0
}

function Get-PythonCandidates {
    $candidates = @()

    # The `py` launcher is installed to a fixed system location by the
    # official python.org installer and found via the registry, so it works
    # even when PATH wasn't updated (the installer's "Add to PATH" checkbox
    # was unchecked). Newest first, since if several are installed we want
    # the newest one that actually works.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.13", "3.12", "3.11", "3.10")) {
            $candidates += [PSCustomObject]@{ Exe = "py"; Args = @("-$v") }
        }
    }

    # Plain PATH lookups. Note: on a machine with no real Python installed,
    # `python`/`python3` on PATH are usually the Microsoft Store's app
    # execution alias stubs, not a real interpreter -- confirmed in testing
    # that these exit non-zero (9009) with a "Python was not found..."
    # message when given arguments, rather than popping open the Store, so
    # probing them here is safe. (The Store prompt only appears when the
    # stub is run with no arguments at all.)
    foreach ($name in @("python", "python3")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) {
            $candidates += [PSCustomObject]@{ Exe = $name; Args = @() }
        }
    }

    # Fall back to python.org installer's default install locations, in
    # case PATH has neither the `py` launcher nor a python*.exe on it.
    $glob = Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe"
    Get-ChildItem -Path $glob -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object { $candidates += [PSCustomObject]@{ Exe = $_.FullName; Args = @() } }

    return $candidates
}

New-Item -ItemType Directory -Force -Path $SupportDir | Out-Null
$env:SPEND_TRACKER_DATA_DIR = $SupportDir

# An existing venv from a previous, older/broken interpreter attempt isn't
# good enough just because the directory exists -- validate it, or rebuild.
if ((Test-Path $VenvDir) -and -not (Test-PythonNewEnough $VenvPython)) {
    Remove-Item -Recurse -Force $VenvDir
}

if (-not (Test-Path $VenvDir)) {
    Write-Log "looking for Python $MinPyMajor.$MinPyMinor+"
    $created = $false
    foreach ($candidate in (Get-PythonCandidates)) {
        if (-not (Test-PythonNewEnough $candidate.Exe $candidate.Args)) {
            Write-Log "  $($candidate.Exe) $($candidate.Args): too old, broken, or not a real Python"
            continue
        }
        Write-Log "  $($candidate.Exe) $($candidate.Args): trying venv creation"
        if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
        & $candidate.Exe @($candidate.Args) -m venv $VenvDir *>> $LogFile
        if ($LASTEXITCODE -eq 0) {
            $created = $true
            Write-Log "  $($candidate.Exe): venv created successfully"
            break
        }
    }
    if (-not $created) {
        if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
        Show-Alert "Couldn't set up Spend Tracker's Python environment -- no Python $MinPyMajor.$MinPyMinor+ install was found working. Install Python 3 from python.org, then relaunch Spend Tracker. (Details in $LogFile)"
        exit 1
    }
}

& $VenvPython -m pip install -q -r (Join-Path $AppDir "requirements.txt") *>> $LogFile
if ($LASTEXITCODE -ne 0) {
    $lastError = (Get-Content $LogFile -Tail 3 -ErrorAction SilentlyContinue) -join " "
    if (-not $lastError) { $lastError = "see $LogFile for details" }
    Show-Alert "Couldn't install Spend Tracker's dependencies: $lastError"
    exit 1
}

# Self-update check/apply lands here in a later change (see
# packaging/update_check.sh on macOS for the reference design).

& $VenvPython (Join-Path $AppDir "src\spend_tracker\desktop_app.py")
