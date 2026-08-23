#!/bin/sh
# Reads .env, substitutes into config.template.yaml, writes data/.config.yaml.
# Run this after editing .env, then: docker compose restart
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "no .env here. copy .env.example to .env and fill it in."; exit 1; }
mkdir -p data
python3 - <<'PY'
import os, re, sys
env = {}
for line in open('.env', encoding='utf-8'):
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

tpl = open('config.template.yaml', encoding='utf-8').read()
missing = [k for k in re.findall(r'\$\{(\w+)\}', tpl) if not env.get(k)]
if missing:
    print('These are still blank in .env: ' + ', '.join(sorted(set(missing))))
    sys.exit(1)

out = re.sub(r'\$\{(\w+)\}', lambda m: env[m.group(1)], tpl)
open('data/.config.yaml', 'w', encoding='utf-8', newline='\n').write(out)
print('wrote data/.config.yaml')
PY
