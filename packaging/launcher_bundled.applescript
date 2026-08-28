-- Launcher for the standalone, distributable build (see build_release.sh).
-- Unlike the dev-mode launcher.applescript at the repo root, this app
-- bundle carries its own copy of the source (Contents/Resources/app/) so it
-- keeps working after being unzipped anywhere on someone else's Mac —
-- nothing outside the .app itself needs to exist.
on run
	my launchApp()
end run

on reopen
	my launchApp()
end reopen

on launchApp()
	set appPath to POSIX path of (path to me)
	set launchScript to appPath & "Contents/Resources/app/launch_app.sh"
	do shell script "nohup " & quoted form of launchScript & " > /tmp/spend-tracker.log 2>&1 &"
end launchApp
