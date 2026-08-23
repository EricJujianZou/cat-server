# Windows entry point. Everything real happens in WSL, because that is where
# Docker runs, so this just forwards the arguments there.
#
#   .\cat.ps1 list          what profiles exist
#   .\cat.ps1 use desk-cat  build that profile and restart the server
#   .\cat.ps1 show          what is running now
#   .\cat.ps1 logs          follow the server log
#   .\cat.ps1 status        is it up, is it reachable

$ErrorActionPreference = 'Stop'
$repo = '/mnt/c/Users/zouju/Coding Projects/cat-server'
$sub  = if ($args.Count -gt 0) { $args[0] } else { 'help' }
$rest = if ($args.Count -gt 1) { $args[1..($args.Count-1)] -join ' ' } else { '' }

switch ($sub) {
  'logs' {
    wsl.exe -e sh -c "cd '$repo' && docker compose logs -f --tail 80"
  }
  'status' {
    wsl.exe -e sh -c "cd '$repo' && docker ps --filter name=cat-server --format 'container: {{.Status}}' && python3 tools/build_profile.py show && curl -s -m 5 -o /dev/null -w 'ota endpoint: %{http_code}\n' http://127.0.0.1:8003/xiaozhi/ota/"
  }
  default {
    wsl.exe -e sh -c "cd '$repo' && python3 tools/build_profile.py $sub $rest"
  }
}
