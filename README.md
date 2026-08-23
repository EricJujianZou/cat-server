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
2. `.\cat.ps1 use desk-cat` builds that profile and restarts the server.
3. Point the cat at `http://<your LAN ip>:8003/xiaozhi/ota/` in its Wi-Fi
   config portal, under Advanced.

Everything you would want to change lives in `config/`, one folder per profile.
See [config/README.md](config/README.md).

## What the cat can do

Two separate systems, and they are easy to confuse.

**Its own body.** Speaker volume, screen brightness and screen theme are tools
that live on the cat, not here. When it opens the WebSocket it sends the server
a list of them, and the server hands that list to the model as callable tools.
Nothing in this repo configures that. If the cat is connected, they work. If the
cat says it cannot change its volume, the cause is the connection or the model,
never a missing setting on this side.

**Everything else.** Anything the cat does not physically own has to come from
the server. There are two routes.

The first is the plugin folder baked into the image: `web_search`, `get_weather`,
`get_news_from_newsnow`, `play_music`, `change_role`. All of them are turned off
in `config/base.yaml`, and the comment there says why for each one. Short
version: three need keys for Chinese services, the bundled music library is three
Chinese songs, and `change_role` overwrites the English cat persona. Turning any
of them on means the model is told it can do something it will then fail at, out
loud, mid-sentence.

The second route is standard MCP servers, and this is the one worth using. List
them in a profile's `config/profiles/<name>/mcp.json` in the usual `mcpServers`
shape and the server starts them and exposes their tools to the model on the
same footing as the cat's own. stdio, SSE and streamable HTTP all work.

The cat's screen is drawn by its own firmware and can only show one of 21 built
in faces, picked by the server sending an emoji. Arbitrary artwork cannot be
pushed to it without reflashing. The list is in
[config/README.md](config/README.md).

## Keeping it running

The container only lives while a WSL session is open. Close the last terminal and
WSL shuts the distro down about twenty seconds later, taking the server with it,
and nothing brings it back until someone opens WSL again. Measured: the OTA
endpoint answered 200 twice, then went dead ten seconds after the last `wsl.exe`
process was killed, and stayed dead for the next eighty seconds.

The fix is one line in `%USERPROFILE%\.wslconfig`:

```ini
[experimental]
vmIdleTimeout=-1
```

Then `wsl --shutdown` once so it takes effect. The alternative is a Windows
scheduled task at logon that runs `wsl.exe -d Ubuntu -e sleep infinity`, which
does the same thing with more moving parts.

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

The container runs on host networking rather than a published port map. Docker's
bridge does not survive `networkingMode=mirrored`: the proxy listens, but nothing
behind it answers. On host networking the server binds the LAN address itself.

Windows blocks inbound traffic to WSL by default, through a separate Hyper-V
firewall whose `DefaultInboundAction` is `Block`. Two rules open just these
ports, and they need an elevated shell:

```powershell
$vm = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
New-NetFirewallHyperVRule -Name cat-server-ws   -DisplayName 'cat-server WebSocket 8000' -Direction Inbound -VMCreatorId $vm -Protocol TCP -LocalPorts 8000 -Action Allow
New-NetFirewallHyperVRule -Name cat-server-http -DisplayName 'cat-server HTTP 8003'      -Direction Inbound -VMCreatorId $vm -Protocol TCP -LocalPorts 8003 -Action Allow
```

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
