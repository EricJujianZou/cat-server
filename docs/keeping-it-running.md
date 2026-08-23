# Keeping it running

The server dies whenever no terminal is open, and this is the single thing
standing between a working demo and a cat that actually lives on the desk.

## What happens

WSL begins shutting the distro down about twenty seconds after the last session
closes. systemd stops `docker.service` on the way down and the container goes
with it. Opening a new terminal aborts the shutdown and starts docker again,
which is why the container looked like it restarted itself every time anyone
touched WSL.

Measured, in `journalctl -u docker`:

```
17:57:11  Started docker.service
17:57:27  Stopping docker.service        <- twenty seconds after the last wsl.exe exited
17:57:28  Stopped docker.service
17:57:35  Starting docker.service        <- the moment the next one opened
```

Probed from Windows with no WSL activity at all, the OTA endpoint answered twice
and then went dead for eighty seconds and did not come back.

## What does not fix it

`vmIdleTimeout=-1` under `[experimental]` in `.wslconfig`. It was set, WSL was
shut down so it took effect, and the container died on the same schedule. The
comment in `%USERPROFILE%\.wslconfig` records this so nobody tries it twice.

## What does fix it

One WSL session held open forever. Verified: with this running, the server
stayed up through eighty four seconds of no terminal activity, where before it
died after twenty.

```powershell
Start-Process -FilePath 'wsl.exe' `
  -ArgumentList '-d','Ubuntu','--exec','/usr/bin/sleep','infinity' `
  -WindowStyle Hidden
```

That covers the current session only. To survive a reboot it needs to be a
scheduled task, and registering one is the one step that has to be run by hand:

```powershell
$action  = New-ScheduledTaskAction -Execute 'wsl.exe' `
             -Argument '-d Ubuntu --exec /usr/bin/sleep infinity'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
             -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
             -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'cat-server-wsl-keepalive' `
  -Action $action -Trigger $trigger -Settings $set -Force `
  -Description 'Holds one WSL session open so cat-server keeps running.'
```

To check it later:

```powershell
Get-ScheduledTask -TaskName 'cat-server-wsl-keepalive'
.\cat.ps1 status
```

To undo the whole thing:

```powershell
Unregister-ScheduledTask -TaskName 'cat-server-wsl-keepalive' -Confirm:$false
Get-Process wsl | Where-Object { $_.CommandLine -like '*sleep infinity*' } | Stop-Process
```

## This goes away on a VPS

None of it exists on a Linux host. The reason is WSL's own session lifetime, so
moving the server to a small VPS removes the problem rather than working around
it, and also removes the requirement that a laptop be awake for the cat to work.
