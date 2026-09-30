# Windows entry point. Most of it happens in WSL, because that is where Docker
# runs, so those subcommands just forward the arguments there. The two helpers
# under `watch` have to stay on Windows, because that is where Claude Code and
# ccpet write their state.
#
#   .\cat.ps1 list          what profiles exist
#   .\cat.ps1 use desk-cat  build that profile and restart the server
#   .\cat.ps1 show          what is running now
#   .\cat.ps1 status        is it up, is it reachable, are the helpers running
#   .\cat.ps1 logs          follow the server log
#   .\cat.ps1 talk          type at the cat and read what it says back, no
#                           hardware and no microphone needed
#   .\cat.ps1 watch         start the two Windows helpers the claude-voice
#                           profile needs, detached so they outlive this window
#   .\cat.ps1 unwatch       stop them again
#   .\cat.ps1 rituals       start the daemon that makes the cat speak first at
#                           the times in config/rituals.yaml, detached like the
#                           watch helpers. `rituals stop` and `rituals status`
#                           do what they say
#   .\cat.ps1 callout       start the listener that has the phone call him out
#                           out loud at bubble tea shops. `callout stop`,
#                           `callout status` and `callout test`, which sends
#                           the trigger email once. See docs/callouts.md
#   .\cat.ps1 dash          open the dashboard in a browser: what the cat is,
#                           every setting as a named field, the log, the voices,
#                           and a box to test a change without the hardware
#   .\cat.ps1 screen        ask the connected cat whether its firmware can draw
#                           your own images. Read only. See
#                           docs/pictures-on-the-screen.md

$ErrorActionPreference = 'Stop'
$repoWin = Split-Path -Parent $MyInvocation.MyCommand.Path
# Same folder, spelled the way WSL sees it, so the script works from wherever
# it was cloned rather than only from the machine it was written on.
$repo    = '/mnt/' + $repoWin.Substring(0,1).ToLower() + $repoWin.Substring(2).Replace('\', '/')
$sub     = if ($args.Count -gt 0) { $args[0] } else { 'help' }
$rest    = if ($args.Count -gt 1) { $args[1..($args.Count-1)] -join ' ' } else { '' }

# The helpers need a real CPython, not the MSYS2 one that `python` resolves to.
function Get-Py {
  foreach ($candidate in @('3.13', '3.12', '3')) {
    try {
      $null = & py "-$candidate" -c "import sys" 2>$null
      if ($LASTEXITCODE -eq 0) { return @('py', "-$candidate") }
    } catch { }
  }
  return @('python')
}

function Helper-Running($needle) {
  $procs = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue
  return @($procs | Where-Object { $_.CommandLine -like "*$needle*" })
}

switch ($sub) {

  'talk' {
    # Type at the server the way the real cat would, so a profile can be tried
    # without the hardware. Only the output encoding is touched here: setting
    # [Console]::InputEncoding as well severs a piped stdin, so a line fed in
    # from a script never reaches the cat.
    $prevOut = [Console]::OutputEncoding
    try {
      [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
      wsl.exe -e sh -c "cd '$repo' && PYTHONIOENCODING=utf-8 python3 tools/fake_cat.py $rest"
    } finally {
      [Console]::OutputEncoding = $prevOut
    }
  }

  'logs' {
    wsl.exe -e sh -c "cd '$repo' && docker compose logs -f --tail 80"
  }

  'watch' {
    $py = Get-Py
    $helpers = @(
      @{ script = 'tools\claude_status_agent.py'; needle = 'claude_status_agent'; what = 'answers what Claude is doing' },
      @{ script = 'tools\claude_watch.py';        needle = 'claude_watch';        what = 'puts session state on the cat face' }
    )
    foreach ($h in $helpers) {
      if ((Helper-Running $h.needle).Count -gt 0) {
        Write-Host "already running: $($h.script)"
        continue
      }
      # The repo path has a space in it, so the script argument has to carry its
      # own quotes or Start-Process splits it in half and python opens nothing.
      $argList = @($py[1..($py.Count-1)]) + @('"' + (Join-Path $repoWin $h.script) + '"')
      Start-Process -FilePath $py[0] -ArgumentList $argList `
        -WorkingDirectory $repoWin -WindowStyle Hidden
      Write-Host "started: $($h.script)  ($($h.what))"
    }
  }

  'unwatch' {
    foreach ($needle in @('claude_status_agent', 'claude_watch')) {
      $found = Helper-Running $needle
      foreach ($p in $found) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "stopped: $needle"
      }
      if ($found.Count -eq 0) { Write-Host "not running: $needle" }
    }
  }

  'rituals' {
    # The daemon that makes the cat speak first, at the times listed in
    # config/rituals.yaml. It runs on Windows like the watch helpers, because
    # that is where the sibling repo and the local clock are.
    $script = 'tools\rituals.py'
    switch ($rest) {
      'stop' {
        $found = Helper-Running 'rituals'
        foreach ($p in $found) {
          Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
          Write-Host "stopped: $script"
        }
        if ($found.Count -eq 0) { Write-Host "not running: $script" }
      }
      'status' {
        $state = if ((Helper-Running 'rituals').Count -gt 0) { 'running' } else { 'stopped, start it with .\cat.ps1 rituals' }
        Write-Host "rituals daemon: $state"
      }
      default {
        if ((Helper-Running 'rituals').Count -gt 0) {
          Write-Host "already running: $script"
        } else {
          $py = Get-Py
          # Same quoting dance as `watch`: the repo path has a space in it.
          $argList = @($py[1..($py.Count-1)]) + @('"' + (Join-Path $repoWin $script) + '"')
          Start-Process -FilePath $py[0] -ArgumentList $argList `
            -WorkingDirectory $repoWin -WindowStyle Hidden
          Write-Host "started: $script  (speaks the rituals in config/rituals.yaml)"
        }
      }
    }
  }

  'callout' {
    # Listens for OwnTracks location reports from the phone over Tailscale and
    # emails the trigger that makes the phone speak. Windows side, because
    # Tailscale runs there and WSL does not see inbound traffic.
    $script = 'tools\callout.py'
    switch ($rest) {
      'stop' {
        $found = Helper-Running 'callout'
        foreach ($p in $found) {
          Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
          Write-Host "stopped: $script"
        }
        if ($found.Count -eq 0) { Write-Host "not running: $script" }
      }
      'status' {
        $state = if ((Helper-Running 'callout').Count -gt 0) { 'running' } else { 'stopped, start it with .\cat.ps1 callout' }
        Write-Host "callout listener: $state"
      }
      'test' {
        $py = Get-Py
        & $py[0] @($py[1..($py.Count-1)]) (Join-Path $repoWin $script) --send-test
      }
      default {
        if ((Helper-Running 'callout').Count -gt 0) {
          Write-Host "already running: $script"
        } else {
          $py = Get-Py
          $argList = @($py[1..($py.Count-1)]) + @('"' + (Join-Path $repoWin $script) + '"')
          Start-Process -FilePath $py[0] -ArgumentList $argList `
            -WorkingDirectory $repoWin -WindowStyle Hidden
          Write-Host "started: $script  (log in data\callout.log)"
        }
      }
    }
  }

  'status' {
    wsl.exe -e sh -c "cd '$repo' && docker ps --filter name=cat-server --format 'container: {{.Status}}' && python3 tools/build_profile.py show && curl -s -m 5 -o /dev/null -w 'ota endpoint: %{http_code}\n' http://127.0.0.1:8003/xiaozhi/ota/"
    foreach ($h in @(
      @{ needle = 'claude_status_agent'; label = 'status agent';   start = 'watch' },
      @{ needle = 'claude_watch';        label = 'face watcher';   start = 'watch' },
      @{ needle = 'rituals';             label = 'rituals';        start = 'rituals' },
      @{ needle = 'callout';             label = 'callout';        start = 'callout' }
    )) {
      $state = if ((Helper-Running $h.needle).Count -gt 0) { 'running' } else { "stopped, start it with .\cat.ps1 $($h.start)" }
      Write-Host ("{0,-14}{1}" -f ($h.label + ':'), $state)
    }
  }

  'screen' {
    # Asks the cat for the tools it hides from the model, two of which would put
    # custom artwork on its screen. It has to be connected, and it hangs up a
    # few minutes after a conversation, so wake it first.
    $prevOut = [Console]::OutputEncoding
    try {
      [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
      wsl.exe -e sh -c "cd '$repo' && PYTHONIOENCODING=utf-8 python3 tools/probe_screen.py $rest"
    } finally {
      [Console]::OutputEncoding = $prevOut
    }
  }

  'dash' {
    # The dashboard runs in WSL, next to docker, and opens the browser on the
    # Windows side itself once it has the port. Ctrl-c here stops it.
    wsl.exe -e sh -c "cd '$repo' && python3 tools/dashboard/server.py $rest"
  }

  default {
    wsl.exe -e sh -c "cd '$repo' && python3 tools/build_profile.py $sub $rest"
  }
}
