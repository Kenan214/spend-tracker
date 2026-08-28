-- The compiled applet stays resident after launch (it doesn't quit once
-- `run` finishes), so a later click on its Dock icon sends `reopen`, not
-- `run` again. Both need to trigger the launch, and the shell command is
-- backgrounded (trailing &) so this handler returns immediately rather than
-- blocking for as long as the app window stays open — AppleScript apps are
-- single threaded, so a blocking call here would leave the app unable to
-- respond to being reopened until the window closes.
--
-- Path is resolved from the app bundle's own location (`path to me`) rather
-- than hardcoded, so this app keeps working if the repo — and this app
-- alongside it — gets moved, without needing a rebuild.
on run
	my launchApp()
end run

on reopen
	my launchApp()
end reopen

on launchApp()
	set appPath to POSIX path of (path to me)
	set repoRoot to do shell script "dirname " & quoted form of appPath
	do shell script "nohup " & quoted form of (repoRoot & "/launch_app.sh") & " > /tmp/spend-tracker.log 2>&1 &"
end launchApp
