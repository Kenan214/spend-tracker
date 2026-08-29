@echo off
rem Double-click entry point for the Windows distributable -- delegates to
rem launcher.ps1 for the actual bootstrap/launch logic (arrays, structured
rem error handling, and JSON parsing for the self-updater beat what batch
rem can do). -ExecutionPolicy Bypass affects only this one invocation, not
rem the user's system-wide policy, so double-clicking works without asking
rem anyone to change their machine's script execution settings.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
