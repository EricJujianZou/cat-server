# Speaking first

Until yesterday the cat only ever answered. The bridge could push a sentence
into an open connection, and `.\cat.ps1 watch` used that to announce Claude
Code states, but an idle cat had no open connection to push into. This page
covers the two changes that fixed that: the connection now survives the day,
and a daemon speaks at fixed times.

## Why it could not speak first

Two timers closed the idle connection, one on each end.

The server's timer is `close_connection_no_voice_time` in `config/base.yaml`.
It used to be two minutes of silence, so a cat sitting powered on and idle
had no connection at all. It is now 86400 seconds and the server keeps the
socket for a day.

The firmware brings its own timer, and that one is the harder problem.
`protocol.cc` marks the audio channel
dead 120 seconds after the last packet the device received from the server,
under the name `kTimeoutSeconds`, and that number is compiled into the device.
No config on this side changes it. Raising the server timeout alone gets a
socket the server is happy to keep and the cat has already abandoned.

So a ritual firing at 08:20 would find nobody to talk to unless someone had
woken the cat in the previous two minutes.

## The keepalive

The firmware's timer resets on any application-level JSON frame. A
transport-level websocket ping does nothing, because the firmware's
application layer never sees one. So every 90 seconds the push bridge sends
each connected cat the face it is already showing, using the same `llm`
message that `POST /face` sends. The firmware redraws the face it is already
drawing and the timer starts over. 90 sits inside 120 with room for a slow
send. The code is in `patches/push_bridge.py`, and `patches/README.md` has
the short version.

`PUSH_KEEPALIVE_SECONDS` in the container's environment changes the interval.
`0` turns it off, which together with the old `close_connection_no_voice_time`
value puts the whole behavior back the way it was.

### What could go wrong

In order of consequence, worst first.

1. **The device can hang on flaky wifi.** The upstream firmware has a known
   issue where a connection that cannot drain buffers data in device memory
   until the device locks up. A socket held open all day with traffic on it
   gives that failure more chances than a socket that lives two minutes at a
   time. If the cat starts freezing, turn the keepalive off first.
2. **None of this has run on the real cat yet.** The keepalive was written
   against the firmware source, and `tools/fake_cat.py` does not enforce the
   120 second timer, so nothing local can prove it works. Until a real cat
   sits connected through a quiet hour, treat the whole chain as unproven.
3. **The face might twitch.** Re-sending the current face is invisible on the
   fake device. The real screen redraws on that frame, and whether the redraw
   is visible as a flicker every 90 seconds is unknown until someone watches
   for it.

The proper long-term route is different from all of this. The firmware also
speaks an MQTT-based transport meant exactly for a server that wants to reach
a sleeping device, and a gateway for it would make the whole keepalive
unnecessary. That is future work, listed at the bottom.

## The rituals daemon

`tools/rituals.py` is a Windows daemon, started detached with
`.\cat.ps1 rituals`. `rituals stop` and `rituals status` do what they say. It
runs on Windows rather than in the container because the sibling repo it
checks and the local clock both live there.

It reads `config/rituals.yaml`, which defines five rituals today:

| Ritual | Time | What it says |
|---|---|---|
| `weight` | 08:20 | asks for the morning weigh-in, mentioning the last recorded number |
| `morning_plan` | 08:30 | says good morning and asks for the day's plan, using yesterday's outcomes |
| `news` | 08:35 | compresses headlines from three RSS feeds into a few spoken sentences |
| `afternoon_review` | 17:30 | reads back the morning plan and asks what actually got done |
| `post_check` | 20:00 | checks `content-machine` for a commit made today, and only speaks when there is none |

Every 30 seconds it checks the clock. When a ritual's time arrives it builds
the spoken line by filling the ritual's prompt template with context from the
ledger, then asking OpenAI to turn that into speech-shaped sentences. If the
model call fails, or the key is missing, it speaks a plain hardcoded fallback
line instead, because a ritual that crashes is worse than one that speaks
plainly. `post_check` runs `git log --since midnight` in
`C:\Users\zouju\Coding Projects\content-machine` and stays quiet when a
commit exists, unless `on_done` is set to `congratulate`.

The finished line goes to the push bridge as `POST /say` on
`127.0.0.1:8004`. When no cat is connected the bridge answers 503, and the
daemon retries every 5 minutes for up to 45. If the cat never shows up it
writes a `missed` row to the ledger and moves on to the next ritual. Both
numbers are `retry_minutes` and `give_up_minutes` in `rituals.yaml`.

Three behaviors worth knowing about:

- **It does not repeat itself after a restart.** The ledger is the record of
  what already spoke or was missed today, so a daemon restarted at noon skips
  the morning rituals rather than running them late.
- **Edits apply without a restart.** It watches `rituals.yaml` for changes
  and reloads within about a minute. An open retry window keeps its old
  settings; the new config applies from the next ritual on.
- **It has a heartbeat.** Every 30 seconds it rewrites
  `data/.rituals-heartbeat` with a timestamp and the enabled ritual names, so
  the dashboard and anything else can tell a running daemon from a stopped
  one by the file's age.

`py -3.13 tools\rituals.py --dry-run` builds every enabled line right now,
prints it, and posts nothing, which is the way to see what a ritual would say
without waiting for its time.

## The desk reminder

The same daemon carries one behavior that runs on presence rather than the
clock. Windows records the moment of the last keyboard or mouse input, and
the daemon reads that every 30 seconds. Twenty minutes of sitting at the desk
and the cat asks for a look out the window, then asks again every twenty
minutes until the owner tells it he looked. The model records that
acknowledgment through the `looked_outside` ledger tool, and the daemon sees
the row and restarts the clock from there. An hour with no input at all ends
the stretch without a word, and the next keypress starts a fresh clock.

The knobs live in the `presence` block of `config/rituals.yaml`:
`remind_minutes`, `away_minutes`, `enabled`, and the prompt the model turns
into the spoken line. Reminders do not get the rituals' retry window. A cat
that is unreachable or mid-conversation is tried again half a minute later,
and an acknowledgment or an away hour cancels the attempt. Spoken reminders
go into the ledger as `reminder` rows, which the dashboard and `get_context`
both leave out of what they show.

Two things it cannot tell apart. Reading or watching something without
touching anything looks like being away, so a reminder can arrive late after
a passive stretch. And any input counts as being at the desk, meetings
included, which is the owner's stated preference.

## The ledger

`data/companion.db` is a sqlite file with one table, `log`, four columns:
`ts`, `kind`, `text`, `data`. Everything the companion knows about the
owner's days goes through it. Only two things write to it, the MCP server
below and the rituals daemon. The dashboard reads it.

`tools/mcp/companion_mcp.py` runs inside the container as a stdio MCP server,
registered in `config/profiles/claude-voice/mcp.json`, and gives the model
nine tools:

| Tool | Does |
|---|---|
| `log_plan` | records the day's stated plan, in the owner's words |
| `log_outcome` | records what got done, with the model's own 0 to 1 estimate of how much of the plan happened |
| `log_weight` | records a weight in kg, lb or jin, normalized to kg |
| `log_idea` | records an idea and answers with the closest past ideas, ranked by word overlap, each with its date |
| `log_note` | records an end of day thought that fits no other kind |
| `focus_start` | opens a focus block with minutes and intent |
| `focus_end` | closes the newest open block with the outcome, updating the row that opened it |
| `looked_outside` | records that the owner looked out the window, resetting the desk reminder clock |
| `get_context` | the recent record: each day's plan and outcome, the 30 day completion rate, the weight trend, any open focus block |

The persona prompt in `config/profiles/claude-voice/prompt.md` tells the
model when to call each one, so saying "I plan to finish the parser today" at
the cat gets logged without anyone naming a tool.

One decision in there needs its reason written down. The database runs with
`journal_mode=DELETE`, on purpose. The file is shared by the container, WSL
tools and Windows processes through the drive mount, and WAL keeps its state
in shared memory that does not work across that boundary. The moment one side
holds a WAL connection, the others get "disk I/O error". Plain journaling
with a busy timeout is fine at a few writes a day, so anything that opens
this file should set the same pragma and keep its connections short.

The dashboard's progress tab renders this ledger and never writes to it.

## What is not built yet

- **An MQTT transport.** The keepalive is a workaround. The firmware's
  MQTT-based protocol is the route a server should use to reach a device that
  is not holding a websocket open, and a gateway for it does not exist here
  yet.
- **Keepalive validation on the real cat.** See the risk list above. One
  quiet connected hour on real hardware settles it.
- **The audio static fix.** Half done. The device reports itself in the
  server log as `echoear-v2` firmware 2.0.4.4 (in the MCP initialize reply),
  which is Espressif's EchoEar hardware on a factory build of the upstream
  firmware. One cause is fixed: the image encoded outgoing speech at 24000 Hz
  while the cat declares 16000, and base.yaml now pins them to agree. If
  static persists at the starts of sentences, the remaining suspect is Edge
  TTS itself: it returns MP3, whose decoder warm-up gets chopped into the
  first opus frames, and the documented cure upstream
  (xinnan-tech/xiaozhi-esp32-server issue 3216) is a different TTS provider,
  which is a voice decision, not a config one. Static only at high volume
  means amp clipping instead: keep volume under about 70.
- **A cloned voice.** Everything today is Edge TTS stock voices.
- **Real semantic memory.** The server's `Memory` module is `nomem` in
  `config/base.yaml`, so between connections the model keeps nothing beyond
  what the ledger tools hand back.
- **A phone voice line over Tailscale**, so the companion works away from the
  desk.
- **Calendar warnings**, spoken before an event rather than at fixed times.
- **Roommate voiceprints**, so the cat knows who is talking to it.
