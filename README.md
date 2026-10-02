# cat-server

Self-hosted brain for the xiaozhi cat, so it stops talking to the seller's
server at `101.35.234.159` and talks to this machine instead.

## What runs where

The cat opens a WebSocket to this server when it is woken and streams compressed
audio down it. Speech recognition, the model, and speech synthesis all happen
here. The cat itself only does wake-word detection, echo cancellation, and
drawing its own face. It never sees text in either direction.

The socket now stays open through idle time, so the server can start a
conversation without waiting for a wake word: its own silence timeout is
raised to a day in `config/base.yaml`, and a keepalive in the push bridge
resets the two minute timer the firmware runs on its side.
[docs/speaking-first.md](docs/speaking-first.md) covers both timers and what
the keepalive risks. When the connection does drop, the cat reopens it on the
next wake word, and the dashboard calls that state idle rather than
disconnected.

## Setup

1. Put your keys in `.env`. It is gitignored and never leaves this machine.
2. Build the image once, inside WSL:
   `docker build -f Dockerfile.slim -t cat-server:slim .`
   This takes the 10.6GB upstream image and drops the packages this config never
   imports, which is most of them. See [docs/slim-image.md](docs/slim-image.md).
3. `.\cat.ps1 use desk-cat` builds that profile and restarts the server.
4. Point the cat at `http://<your LAN ip>:8003/xiaozhi/ota/` in its Wi-Fi
   config portal, under Advanced.

Everything you would want to change lives in `config/`, one folder per profile.
See [config/README.md](config/README.md).

## What the cat can do

Two separate systems, and they are easy to confuse.

**Its own body.** These tools live on the cat, not here. When it opens the
WebSocket it sends the server a list of them, and the server hands that list to
the model as callable tools. Nothing in this repo configures that. If the cat is
connected, they work. If the cat says it cannot change its volume, the cause is
the connection or the model, never a missing setting on this side.

The list is the firmware's, so it varies by board and by firmware version. This
is what the cat on this desk announced, read out of the server log:

| Tool | What it does |
|---|---|
| `self_get_device_status` | battery, volume, brightness, network, whatever the board tracks |
| `self_audio_speaker_set_volume` | speaker volume, 0 to 100 |
| `self_screen_set_brightness` | screen brightness, 0 to 100 |
| `self_screen_set_theme` | light or dark |
| `self_timer_manage` | set, list and cancel timers on the device |
| `self_online_music_play_music` | play a track from the firmware's own music service |
| `self_online_music_control_playback` | pause, resume, skip |
| `self_online_music_manage_playlist` | add and remove tracks |
| `self_sys_get_new_message` | read messages the firmware has queued |
| `self_sys_get_verification_code` | the pairing code for the seller's app, unused here |

Fifteen more come from the server side. `handle_exit_intent`, which lets the
model end the conversation itself, and `get_lunar`, which answers lunar
calendar questions, are always present. The `claude-voice` profile turns on
two bundled plugins, `web_search` and `play_music`, and its two MCP servers
add the other eleven: `claude_status` and `claude_sessions` for watching
Claude Code, and nine ledger tools for logging plans, outcomes, weight,
ideas, notes, focus blocks and look-outside acknowledgments, described in
[docs/speaking-first.md](docs/speaking-first.md). Twenty-five in total on
this setup.

Two of these are worth knowing about. `self_timer_manage` means kitchen timers
already work with no server-side work at all. `handle_exit_intent` is why saying
"close the connection" in English ends the session even though the configured
exit commands are Chinese only: the model calls the tool rather than matching a
phrase.

To see the live list rather than this table, look for `当前支持的函数列表` in
`.\cat.ps1 logs`.

**Everything else.** Anything the cat does not physically own has to come from
the server. There are two routes.

The first is the plugin folder baked into the image: `web_search`, `get_weather`,
`get_news_from_newsnow`, `play_music`, `change_role`. All of them are off in
`config/base.yaml`, and the comment there says why for each one. The rule is
that the model is never told it can do something it will then fail at, out
loud, mid-sentence. Two have since earned their way on, in `claude-voice`
only: `web_search` with a Tavily key, and `play_music`, which plays whatever
is in the repo's `music/` folder through the cat's speaker.

The second route is standard MCP servers, and this is the one worth using. List
them in a profile's `config/profiles/<name>/mcp.json` in the usual `mcpServers`
shape and the server starts them and exposes their tools to the model on the
same footing as the cat's own. stdio, SSE and streamable HTTP all work.

The cat's screen is drawn by its own firmware and can only show one of 21 built
in faces, picked by the server sending an emoji. Arbitrary artwork cannot be
pushed to it without reflashing. The list is in
[config/README.md](config/README.md).

## Keeping it running

The server only lives while a terminal is open. WSL starts shutting the distro
down about twenty seconds after the last session closes, systemd stops docker on
the way down, and the container goes with it. The fix is a scheduled task at
logon holding one WSL session open, and it is the one setup step that has to be
run by hand. [docs/keeping-it-running.md](docs/keeping-it-running.md) has the
measurements and the command.

## Profiles

Same hardware, same server, different config. `.\cat.ps1 list` shows what
exists.

| Profile | What it is for |
|---|---|
| `desk-cat` | Plain talking companion, no tools. The fallback when something breaks. |
| `claude-voice` | Ask what Claude Code is doing, and watch it on the cat's face. Needs `.\cat.ps1 watch` running. |

Everything a profile is lives in `config/profiles/<name>/`: a prompt, a voice,
and a list of MCP servers. See [config/README.md](config/README.md).

## Testing without the hardware

`.\cat.ps1 talk` connects the way the real device does and lets you type at the
cat, printing everything the server sends back: which face it asked for, every
sentence it spoke, and how much audio came out. No microphone and no cat needed.

```powershell
.\cat.ps1 talk                          # type at it until ctrl-c
.\cat.ps1 talk "what time is it"        # say one thing and exit
.\cat.ps1 talk --listen                 # watch what the server pushes
```

Type in whatever language you like. Speech recognition is OpenAI's and handles
Chinese, but the reply comes back in whatever `language` the profile sets, which
is English on both profiles today. See [config/README.md](config/README.md).

Inside WSL the same thing is `python3 tools/fake_cat.py`.

## Making it speak first

`.\cat.ps1 rituals` starts a Windows daemon that has the cat speak on its own
at the times in `config/rituals.yaml`: a morning weigh-in, the day's plan, the
news, an afternoon review of that plan, and an evening check that today's post
got committed. `rituals stop` and `rituals status` do what they say. When no
cat is connected at ritual time the daemon retries for forty five minutes and
then records the miss. [docs/speaking-first.md](docs/speaking-first.md) has
the whole chain, including the keepalive that holds the connection open long
enough to be spoken into.

## Where the keys go

One key does both jobs.

| Key | What it does | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | Turns your voice into text, and answers | platform.openai.com |

Text to speech uses Edge TTS, which needs no key and costs nothing.

To put Claude back in as the brain instead, add an `ANTHROPIC_API_KEY` and point
the `OpenAILLM` block at `https://api.anthropic.com/v1` with a Claude model
name. Anthropic has no speech to text, so the OpenAI key stays either way.

Never put a key in `config/`. That whole folder is committed. `.env` and the
built `data/.config.yaml` are both ignored.

### Why it cannot search the web or read the weather

Both are real plugins in the server image, and both are switched off because
neither has a key that works here.

| Plugin | Needs | Why it is off |
|---|---|---|
| `web_search` | a Metaso or Tavily key | The image ships the literal string `mk-xxx`. |
| `get_weather` | a QWeather key and host | The shared key is rate limited and the default city is Guangzhou. |
| `get_news_from_newsnow` | nothing | The sources are Chinese. |
| `play_music` | files in `music/` | On in `claude-voice`. Off elsewhere so an empty library is never promised. |
| `change_role` | nothing | It replaces the profile's persona with a Chinese one. |

Leaving them on is worse than leaving them off, because the model is told it can
search and then fails out loud in the middle of a sentence.

Search is the one worth turning on, and it is: the `claude-voice` profile
enables `web_search` against Tavily, with the key read from `TAVILY_API_KEY`
in `.env`. Weather does not need a key at all if it goes through an MCP server
against Open-Meteo instead of the bundled plugin.

## Docs

| | |
|---|---|
| [config/README.md](config/README.md) | Every knob, and how to add a profile |
| [patches/README.md](patches/README.md) | The two mounted files, and what they change |
| [docs/keeping-it-running.md](docs/keeping-it-running.md) | Why it dies, and the one command that fixes it |
| [docs/speaking-first.md](docs/speaking-first.md) | How the cat speaks first: the two timeouts, the keepalive, the rituals, the ledger |
| [docs/slim-image.md](docs/slim-image.md) | 10.6GB down to 1.3GB, what came out and how it was checked |
| [docs/ccpet-on-the-cat.md](docs/ccpet-on-the-cat.md) | ccpet states on the cat's face, and why not its artwork |
| [docs/pictures-on-the-screen.md](docs/pictures-on-the-screen.md) | Your own artwork on the screen: what it needs, and what it risks |
| [docs/voice-into-claude.md](docs/voice-into-claude.md) | What `/voice` is, and what talking back would take |
| [docs/use-case-research.md](docs/use-case-research.md) | Who this device is actually for, globally |
| [docs/why-hardware.md](docs/why-hardware.md) | Why not just a phone app, and what the screen would have to become |
| [docs/voices.md](docs/voices.md) | Which voices work, where to hear them, and what a better one would cost |

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
now holds the same address on `eth0` that Windows does.

## Moving to AWS later

The image, the compose file and the config are the same on a Linux host. Change
`HOST_LAN_IP` to the public address, re-render, and change the one URL in the
cat's portal. Nothing about the firmware changes.

## The dashboard

`.\cat.ps1 dash` starts a local page on `http://127.0.0.1:8080/` and opens it.

The bar across the top says the one thing worth knowing before anything else:
whether the server is up, whether the config on disk is what the container is
running, and when the cat last spoke. Click it for the rest, one cell per fact,
worst first.

Five places underneath.

**cat** is everything you change, as named fields rather than YAML. Which
profile is built, the persona, the voice, every tool with a switch, the wake
phrases, the model. Each field says which file its value came from and opens
that file if you click it. At the bottom is a list of the things people look for
here and will not find, with where they actually live, because an absent setting
looks exactly like one you have not found yet.

Tools come in three groups because three different rules apply. MCP servers from
the profile's `mcp.json` switch on and off, and switching one off moves it into
a disabled block rather than deleting it. The five bundled plugins switch too,
each next to the reason it is off. The cat's own `self.*` tools are read only
with the description the firmware gave them, because nothing on this side
configures those.

**voices** is every Edge TTS voice with a play button. The Chinese ones are split
by what they actually speak, so `zh-HK` reads as Cantonese and `zh-CN` as
Mandarin, and the audition text changes to match. Choosing a voice writes both
`voice` and `language` into the profile, because the server hardcodes the output
language into its prompt and a Cantonese voice reading Mandarin is nobody's
language. If the two ever disagree the page says so in red.

**progress** is the ledger in `data/companion.db`, read and never written.
It shows the weight readings, each day's plan next to what actually got done
with the model's completion estimate, the thirty day completion rate, focus
blocks, past ideas, and the rituals that were missed because no cat was
connected. There are no controls here, because the way to put a row in this
tab is to tell the cat something.

**log** is the server log as it happens, with a text filter, a level filter, and
a switch for the listen heartbeats the cat sends every time it opens its
microphone.

**files** is the raw editor, every file under `config/`, for the things no form
will ever cover.

Along the bottom is a test box. Type what you would say out loud and it connects
the way the cat does, then shows the reply, which face the server picked, every
tool the model called with its arguments, and how much audio came back. It is
the only way to see a tool call, and it is how you check that a change worked
without leaving the page. There is a button to hear the reply, which
re-synthesises the text with the profile's voice rather than replaying what the
cat received, and says so.

Rebuilding is a button in the top right and a banner when something is unbuilt.
The banner is worked out from a hash of `config/` against a stamp the builder
writes, so it survives a reload, notices an edit made in an editor, and clears
itself when you rebuild from PowerShell. Undo the edit and it goes away on its
own. While a rebuild runs the page shows which of the four steps it is on, and
it calls the job done only when the server answers on 8003 again rather than
when the subprocess exits.

It never opens `.env` or `data/.config.yaml`. Everything the form reads and
writes is under `config/`, where the keys are still `${PLACEHOLDERS}`. Samples
are rendered by the container's own `edge-tts` and cached under
`tools/dashboard/.cache/`, which is ignored by git.
