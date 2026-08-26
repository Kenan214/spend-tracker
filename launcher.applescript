-- The compiled applet stays resident after launch (it doesn't quit once
-- `run` finishes), so a later click on its Dock icon sends `reopen`, not
-- `run` again. Both need to trigger the launch, and the shell command is
-- backgrounded (trailing &) so this handler returns immediately rather than
-- blocking for as long as the app window stays open — AppleScript apps are
-- single threaded, so a blocking call here would leave the app unable to
-- respond to being reopened until the window closes.
on run
	my launchApp()
end run

on reopen
	my launchApp()
end reopen

on launchApp()
	do shell script "nohup /Users/kenan/Desktop/Repos/spend-tracker/launch_app.sh > /tmp/spend-tracker.log 2>&1 &"
end launchApp
