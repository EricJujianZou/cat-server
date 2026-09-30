# Callouts

The phone speaks a line out loud through its own speaker when he walks into a
bubble tea shop. The cat is not part of it, because the cat stays on the desk.

## How it works

1. OwnTracks on the iPhone posts his location to the PC over Tailscale each
   time iOS wakes it.
2. tools/callout.py, running on Windows, checks the spot against
   OpenStreetMap. Most tea shops there are tagged cuisine=bubble_tea, and a
   list of chain names catches the rest.
3. If he is within 45 metres of one, it emails a trigger to his iCloud
   address.
4. An iPhone Shortcut automation fires on that email, turns the volume to
   100% and speaks the line. The spoken audio uses media volume, so the
   silent switch does not stop it.

It calls out once per shop every four hours, and never twice within 45
minutes. Each callout is written to data/companion.db as kind callout.

The line lives in the Shortcut on the phone. The copy in tools/callout.py
only goes in the email body:

> Look at this sugar addict back at it again with the daily performative ahh matcha

## Setup, once

On the PC:

1. Install Tailscale on the PC and on the iPhone, signed into the same
   account. Note the PC's name in the Tailscale app.
2. Open port 8090 on the Tailscale network only, in an elevated PowerShell:
   `New-NetFirewallRule -DisplayName "cat callout" -Direction Inbound -Protocol TCP -LocalPort 8090 -InterfaceAlias Tailscale -Action Allow`
3. Fill the CALLOUT_ lines in .env. The iCloud app-specific password comes
   from account.apple.com, under Sign-In and Security.
4. Run `.\cat.ps1 callout`, then `.\cat.ps1 callout test`. The email should
   show up in the phone's Mail app within a few seconds.

On the iPhone:

1. Mail has to have the iCloud account switched on, because the automation
   only sees mail in the Mail app.
2. Shortcuts, Automation, New Automation, Email. Set Subject Contains to
   `cat callout`, pick Run Immediately, and turn off Notify When Run. Add two
   actions: Set Volume to 100%, then Speak Text with the line above.
3. Run `.\cat.ps1 callout test` again. The phone should say the line.
4. Install OwnTracks. In its settings set Mode to HTTP and the URL to
   `http://PC-NAME:8090/owntracks`. Turn Authentication on with user `cat`
   and CALLOUT_PASSWORD from .env. Allow location Always, with Precise on.
5. Set the OwnTracks monitoring mode to Move. Significant mode saves battery
   but only reports after about 500 metres of travel, so it usually misses
   the moment he stops inside a shop.

## Checking it

- `.\cat.ps1 callout status` says whether the listener is running.
- data\callout.log has every report that reached a shop, a cooldown, or a
  failure.
- `py -3.13 tools\callout.py --check LAT LON` names the closest tea shop to
  any spot and whether it would fire, without sending anything.
