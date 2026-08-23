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
#   .\cat.ps1 watch         start the two Windows helpers the claude-voice
#                           profile needs, detached so they outlive this window
#   .\cat.ps1 unwatch       stop them again

$ErrorActionPreference = 'Stop'
$repoWin = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo    = '/mnt/c/Users/zouju/Coding Projects/cat-server'
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

  'status' {
    wsl.exe -e sh -c "cd '$repo' && docker ps --filter name=cat-server --format 'container: {{.Status}}' && python3 tools/build_profile.py show && curl -s -m 5 -o /dev/null -w 'ota endpoint: %{http_code}\n' http://127.0.0.1:8003/xiaozhi/ota/"
    foreach ($h in @(
      @{ needle = 'claude_status_agent'; label = 'status agent' },
      @{ needle = 'claude_watch';        label = 'face watcher' }
    )) {
      $state = if ((Helper-Running $h.needle).Count -gt 0) { 'running' } else { 'stopped, start it with .\cat.ps1 watch' }
      Write-Host ("{0,-14}{1}" -f ($h.label + ':'), $state)
    }
  }

  default {
    wsl.exe -e sh -c "cd '$repo' && python3 tools/build_profile.py $sub $rest"
  }
}
