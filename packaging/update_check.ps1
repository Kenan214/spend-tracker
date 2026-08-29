# Self-updater: checks GitHub Releases for a newer version and, if found,
# downloads + stages it under %LOCALAPPDATA%\Spend Tracker\pending_update
# for the *next* launch to apply (see the "apply pending update" block near
# the top of launcher.ps1). Spawned detached, hidden, by the launcher on
# every run -- never blocks app startup, and every step below is
# best-effort: any failure just leaves the current install running
# untouched. No dialogs, no alerts, no exit codes anyone checks.
#
# The trick this relies on: the Zone.Identifier alternate-data-stream that
# triggers Windows' "this file came from another computer" warnings (and
# feeds SmartScreen reputation checks) is attached explicitly by
# quarantine-aware tools -- browsers, Outlook, Explorer's "Extract All"
# wizard. Invoke-WebRequest and Expand-Archive, used below, do neither --
# so a release fetched and extracted this way carries no such mark and
# launches clean next time, no re-approval needed. Same trick Sparkle and
# other third-party auto-updaters use on macOS (see update_check.sh).
param(
    [string]$CurrentVersion = "v0.0.0"
)

$Repo = "Kenan214/spend-tracker"
$SupportDir = Join-Path $env:LOCALAPPDATA "Spend Tracker"
$PendingDir = Join-Path $SupportDir "pending_update"
$LogFile = Join-Path $env:TEMP "spend-tracker-updater.log"
$ThrottleFile = Join-Path $SupportDir "last_update_check"
$ThrottleSeconds = 1800 # don't hit the GitHub API more than every 30 min

function Log([string]$Message) {
    "$(Get-Date): $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Strip-VPrefix([string]$V) {
    if ($V.StartsWith("v")) { return $V.Substring(1) }
    return $V
}

# Compares dotted version numbers numerically (so v0.2.0 > v0.10.0 is
# judged correctly, unlike a plain string compare) -- ported line-for-line
# from update_check.sh's version_gt, including its behavior on non-numeric
# suffixes (e.g. "v0.0.0-ci"'s third component "0-ci" isn't a plain
# integer, so it's treated as 0), to keep both updaters' comparisons
# behaving identically for the same tag.
function Test-VersionGreater([string]$V1, [string]$V2) {
    $a = (Strip-VPrefix $V1) -split "\."
    $b = (Strip-VPrefix $V2) -split "\."
    for ($i = 0; $i -lt 3; $i++) {
        $x = 0; $y = 0
        if ($i -lt $a.Length -and $a[$i] -match "^\d+$") { $x = [int]$a[$i] }
        if ($i -lt $b.Length -and $b[$i] -match "^\d+$") { $y = [int]$b[$i] }
        if ($x -gt $y) { return $true }
        if ($x -lt $y) { return $false }
    }
    return $false
}

New-Item -ItemType Directory -Force -Path $SupportDir | Out-Null

$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
if (Test-Path $ThrottleFile) {
    $last = [int64]0
    $rawLast = Get-Content $ThrottleFile -Raw -ErrorAction SilentlyContinue
    if ($rawLast) { [int64]::TryParse($rawLast.Trim(), [ref]$last) | Out-Null }
    if (($now - $last) -lt $ThrottleSeconds) {
        Log "skipping check, last checked $($now - $last)s ago"
        exit 0
    }
}
Set-Content -Path $ThrottleFile -Value $now -NoNewline -Encoding utf8

# Already have a verified, still-newer update staged from a previous
# launch's check -- nothing to do, it'll be applied next launch.
$StagedVersionFile = Join-Path $PendingDir "VERSION"
if ((Test-Path (Join-Path $PendingDir "READY")) -and (Test-Path $StagedVersionFile)) {
    $staged = $null
    $rawStaged = Get-Content $StagedVersionFile -Raw -ErrorAction SilentlyContinue
    if ($rawStaged) { $staged = $rawStaged.Trim() }
    if ($staged -and (Test-VersionGreater $staged $CurrentVersion)) {
        Log "already have $staged staged, skipping"
        exit 0
    }
}

try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" `
        -Headers @{ Accept = "application/vnd.github+json" } `
        -TimeoutSec 15 -ErrorAction Stop
} catch {
    Log "GitHub API fetch failed: $_"
    exit 0
}

$latestTag = $release.tag_name
if (-not $latestTag) {
    Log "couldn't parse tag_name from API response"
    exit 0
}

if (-not (Test-VersionGreater $latestTag $CurrentVersion)) {
    Log "up to date (running $CurrentVersion, latest is $latestTag)"
    exit 0
}

$asset = $release.assets | Where-Object { $_.name -like "SpendTracker-*-Windows.zip" } | Select-Object -First 1
if (-not $asset) {
    Log "release $latestTag has no SpendTracker-*-Windows.zip asset"
    exit 0
}

Log "newer version available: $latestTag (currently $CurrentVersion), downloading from $($asset.browser_download_url)"
$DlDir = Join-Path $env:TEMP "spend-tracker-update-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $DlDir | Out-Null
try {
    $ZipPath = Join-Path $DlDir "update.zip"
    try {
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $ZipPath -TimeoutSec 180 -ErrorAction Stop
    } catch {
        Log "download failed: $_"
        exit 0
    }

    # This is the load-bearing assumption of the whole feature -- verify
    # it, don't just trust it. Invoke-WebRequest shouldn't attach a
    # Zone.Identifier stream, but strip defensively either way; it costs
    # nothing and it's cheap insurance against some future environment
    # (proxy, corporate MDM/EDR, etc.) behaving differently.
    Unblock-File -Path $ZipPath -ErrorAction SilentlyContinue

    try {
        Expand-Archive -Path $ZipPath -DestinationPath $DlDir -ErrorAction Stop
    } catch {
        Log "extraction failed: $_"
        exit 0
    }

    # No signature to verify -- builds are unsigned (see #6) -- so this
    # structural check is what stands in for macOS's `codesign --verify`:
    # not an authenticity check either way, just a guard against a
    # corrupted or unexpectedly-shaped download getting applied.
    $NewApp = Join-Path $DlDir "Spend Tracker"
    $requiredPaths = @(
        (Join-Path $NewApp "SpendTracker.bat"),
        (Join-Path $NewApp "launcher.ps1"),
        (Join-Path $NewApp "app\src\spend_tracker\desktop_app.py"),
        (Join-Path $NewApp "app\VERSION")
    )
    $missing = $requiredPaths | Where-Object { -not (Test-Path $_) }
    if ($missing) {
        Log "extracted zip missing expected files: $($missing -join ', ')"
        exit 0
    }
    Get-ChildItem -Path $NewApp -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

    $newVersion = $latestTag
    $rawNewVersion = Get-Content (Join-Path $NewApp "app\VERSION") -Raw -ErrorAction SilentlyContinue
    if ($rawNewVersion -and $rawNewVersion.Trim()) { $newVersion = $rawNewVersion.Trim() }

    # Only now -- everything downloaded, extracted, and verified -- touch
    # the real staging dir the launcher looks at, and only mark it READY
    # last, so a half-finished check (killed mid-run, disk full, etc.)
    # never leaves a half-staged update for the launcher to apply.
    Remove-Item -Recurse -Force $PendingDir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $PendingDir | Out-Null
    Move-Item $NewApp (Join-Path $PendingDir "Spend Tracker")
    Set-Content -Path (Join-Path $PendingDir "VERSION") -Value $newVersion -NoNewline -Encoding utf8
    New-Item -ItemType File -Force -Path (Join-Path $PendingDir "READY") | Out-Null
    Log "staged $newVersion, will apply on next launch"
} finally {
    Remove-Item -Recurse -Force $DlDir -ErrorAction SilentlyContinue
}
