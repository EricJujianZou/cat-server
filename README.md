# cat-server

Self-hosted brain for the xiaozhi cat, so it stops talking to the seller's
server at `101.35.234.159` and talks to this machine instead.

## What runs where

The cat holds one WebSocket open to this server and streams compressed audio
down it. Speech recognition, the model, and speech synthesis all happen here. The
cat itself only does wake-word detection, echo cancellation, and drawing its own
face. It never sees text in either direction.

## Setup

1. Put your keys in `.env`. It is gitignored and never leaves this machine.
2. `./render-config.sh` to generate `data/.config.yaml` from the template.
3. `docker compose up -d`
4. Point the cat at `http://<your LAN ip>:8003/xiaozhi/ota/` in its Wi-Fi
   config portal, under Advanced.

## Where the keys go

One key does both jobs.

| Key | What it does | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | Turns your voice into text, and answers | platform.openai.com |

Text to speech uses Edge TTS, which needs no key and costs nothing.

To put Claude back in as the brain instead, add an `ANTHROPIC_API_KEY` and point
the `OpenAILLM` block at `https://api.anthropic.com/v1` with a Claude model
name. Anthropic has no speech to text, so the OpenAI key stays either way.

Never put a key in `config.template.yaml`. That file is committed. `.env` and
the rendered `data/.config.yaml` are both ignored.

## Ports

| Port | Purpose |
|---|---|
| 8000 | WebSocket the cat holds open, carrying audio both ways |
| 8003 | HTTP, serves the endpoint the cat asks at boot |

## Why the cat stops asking for an activation code

The seller's server replies to the boot request with an `activation` block, and
the firmware draws the code screen because it was told to. This server's reply
has no such block, so the cat connects instead. Nothing is reflashed and no
account is involved.

## Networking note

Docker Engine runs inside WSL2. Published ports reach Windows `localhost`
automatically, but the cat connects across the LAN, which needs
`networkingMode=mirrored` in `%USERPROFILE%\.wslconfig` so WSL shares the host's
network interface. That is already set, and confirmed working: the Ubuntu distro
now holds `192.168.4.46` on `eth0`, the same address as Windows.

## Moving to AWS later

The image, the compose file and the config are the same on a Linux host. Change
`HOST_LAN_IP` to the public address, re-render, and change the one URL in the
cat's portal. Nothing about the firmware changes.
