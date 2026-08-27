# CLAUDE.md

Self-hosted brain for a xiaozhi ESP32-S3 cat. Audio comes up a WebSocket, the
server does hearing, thinking and speaking, and streams speech back down. The
upstream server (xinnan-tech/xiaozhi-esp32-server) runs in Docker inside WSL
with two files overlaid from patches/.

## Read these first, ranked by what a wrong assumption costs

1. **README.md**, the system. What runs where, the cat's own tools versus
   server-side ones, ports, WSL networking, why the bundled plugins are off.
   Most bad changes come from not knowing which side owns a behavior.
2. **docs/speaking-first.md**, everything proactive. The two idle timeouts,
   the keepalive, the rituals daemon, the desk reminder, and the ledger in
   data/companion.db with its nine tools. Touch nothing about timing or push
   without reading it.
3. **config/README.md**, every knob and how a profile builds. Edits go in
   config/, never in data/.config.yaml, which is generated and gitignored.
4. **patches/README.md**, the two overlaid files. connection.py is the stock
   file plus a small hook, so upstream image updates can break it.

## Facts that are easy to get wrong

- tools/rituals.py and the dashboard run on Windows Python, which has no yaml
  module. config/rituals.yaml is parsed by a hand-rolled reader, so stick to
  the syntax already in that file.
- Builds and docker live inside WSL. From PowerShell use .\cat.ps1, which
  shells in. `docker compose restart` does not pick up compose file changes,
  that needs `docker compose up -d`.
- Keys live in .env only. Everything under config/ is committed and holds
  ${PLACEHOLDERS}. The build exits if a referenced key is blank in .env.
- The model is never given a tool that will fail out loud. A keyless plugin or
  an empty music library stays switched off. This is a standing rule, not a
  current state.
- desk-cat is the no-tools fallback profile and stays that way. New abilities
  go in claude-voice or a new profile.
- Test without hardware: `.\cat.ps1 talk "..."` or the dashboard test box.
  `.\cat.ps1 dash` serves http://127.0.0.1:8080/.
- The cat's radio is BLE only. No Bluetooth audio in either direction on this
  hardware, and the firmware uses Bluetooth for Wi-Fi setup and nothing else.

## The owner

He directs design and does not read diffs. Report behavior, not code. Copy the
cat will speak out loud is a design decision and gets shown verbatim.

## Design docs, published as artifacts

- Anatomy of the Cat, the as-built map, the memory layers, and the current
  not-built-yet list:
  https://claude.ai/code/artifact/ff8e5995-3a73-4f41-989c-b145f107270a
- The Cat's Jobs, the verdicts and costs behind the choices:
  https://claude.ai/code/artifact/63da2e9f-eb9c-4cf4-ad5e-2d28787c8aab

Both are snapshots. When they disagree with the repo, the repo wins.
