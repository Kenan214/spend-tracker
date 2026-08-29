# Applies a staged update. Started detached by launcher.ps1 from a copy at
# %LOCALAPPDATA%\Spend Tracker\apply_update.ps1 -- a location outside both
# the old install and the staged one, so this script is never mid-rename
# while it's the one executing -- once the launcher process that spawned
# it has exited. Waits for that exit, retries the actual folder swap a few
# times (a fresh AV/EDR scan of newly-written files is a common source of
# a transient sharing-violation on Windows with no real macOS equivalent),
# then relaunches: from the new install on success, from the untouched old
# one if the swap couldn't be completed. Silent and best-effort
# throughout -- never a dialog, never blocks the user from using whichever
# install ends up in place.
param(
    [Parameter(Mandatory = $true)][string]$OldDir,
    [Parameter(Mandatory = $true)][string]$NewDir,
    [Parameter(Mandatory = $true)][int]$OldPid
)

$SupportDir = Join-Path $env:LOCALAPPDATA "Spend Tracker"
$PendingDir = Join-Path $SupportDir "pending_update"
$BackupDir = Join-Path $SupportDir "previous_version"
$LogFile = Join-Path $env:TEMP "spend-tracker-updater.log"

function Log([string]$Message) {
    "$(Get-Date): $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Start-App([string]$Dir) {
    $LauncherPath = Join-Path $Dir "launcher.ps1"
    Start-Process powershell.exe -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $LauncherPath
    ) -WindowStyle Hidden
}

Wait-Process -Id $OldPid -Timeout 10 -ErrorAction SilentlyContinue

# Each attempt only does whichever step hasn't happened yet, so a retry
# after a partial failure (e.g. the first move succeeds but the second
# hits a transient lock) resumes cleanly instead of re-attempting a move
# whose source no longer exists.
$swapped = $false
$lastError = $null
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        if ((Test-Path $OldDir) -and -not (Test-Path $BackupDir)) {
            Move-Item -Path $OldDir -Destination $BackupDir -ErrorAction Stop
        }
        if ((Test-Path $NewDir) -and -not (Test-Path $OldDir)) {
            Move-Item -Path $NewDir -Destination $OldDir -ErrorAction Stop
        }
        if ((Test-Path $OldDir) -and -not (Test-Path $NewDir)) {
            $swapped = $true
            break
        }
    } catch {
        $lastError = $_
        Log "swap attempt $attempt failed: $_"
    }
    Start-Sleep -Milliseconds 500
}

if ($swapped) {
    Log "update applied, cleaning up staging"
} else {
    Log "swap failed after retries ($lastError), restoring original"
    if ((Test-Path $BackupDir) -and -not (Test-Path $OldDir)) {
        Move-Item -Path $BackupDir -Destination $OldDir -ErrorAction SilentlyContinue
    }
}
Remove-Item -Recurse -Force $BackupDir -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $PendingDir -ErrorAction SilentlyContinue

if (Test-Path $OldDir) {
    if ($swapped) {
        Log "relaunching updated install from $OldDir"
    } else {
        Log "relaunching untouched install from $OldDir"
    }
    Start-App $OldDir
} else {
    # Both the swap and the restore failed -- extremely unlikely (would
    # need the original move and the recovery move to both fail), but if
    # it happens there's nothing left to relaunch. Silent per the "no
    # dialogs, ever" rule this script follows throughout; the log is the
    # only record.
    Log "CRITICAL: no install left at $OldDir after failed swap and restore"
}
