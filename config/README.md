# config

Everything that decides what the cat is lives in this folder. Nothing outside it
needs editing to change the cat's personality, voice, model or abilities.

```
config/
  base.yaml                shared by every profile. Server ports, providers, keys.
  rituals.yaml             what the cat says on its own, and when. Read on Windows.
  profiles/
    desk-cat/
      profile.yaml         voice, model, and anything that overrides base.yaml
      prompt.md            the system prompt, verbatim, nothing wrapped around it
      mcp.json             the MCP servers this profile can call
    claude-voice/
      ...
```

## Switching profile

From PowerShell:

```powershell
.\cat.ps1 list             # what exists, and which one is built
.\cat.ps1 use desk-cat     # build it and restart the server
.\cat.ps1 show             # what is running now
.\cat.ps1 status           # is it up, is the endpoint answering
.\cat.ps1 logs             # follow the log
.\cat.ps1 talk             # type at the cat and read what it says back
.\cat.ps1 rituals          # start the daemon that speaks at the times in rituals.yaml
```

From inside WSL, `python3 tools/build_profile.py list | use <name> | show`.

Building a profile writes two files into `data/`, which is the only place the
server reads from:

| Written | From |
|---|---|
| `data/.config.yaml` | `base.yaml` merged with `profile.yaml`, plus `prompt.md` |
| `data/.mcp_server_settings.json` | `mcp.json` |

Both are generated. Editing them by hand works until the next build overwrites
them, so make the change in `config/` instead.

## Making a new profile

Copy an existing folder and edit three files.

```powershell
Copy-Item -Recurse config\profiles\desk-cat config\profiles\my-thing
.\cat.ps1 use my-thing
```

`profile.yaml` needs a `description` line, which is what shows up in
`.\cat.ps1 list`. Everything else in it is optional, and any key you set
replaces the same key in `base.yaml`. Dictionaries merge key by key. Lists
replace outright, so setting a list gives you exactly that list.

## Where the values come from

Secrets are never in this folder. `.env` holds them, and the builder substitutes
them by name where `base.yaml` or a profile writes `${OPENAI_API_KEY}` or
`${HOST_LAN_IP}`. If a name is blank in `.env` the build stops and tells you
which one.

## The language it answers in

The server's prompt template hard-codes an output language, so `language` in
`base.yaml` decides what the cat replies in, not the system prompt. Both
profiles set it to English. Override it in a profile alongside a matching voice:

```yaml
LLM:
  OpenAILLM:
    language: Chinese
TTS:
  EdgeTTS:
    voice: zh-CN-XiaoxiaoNeural
```

Speech recognition needs no such setting. It already understands whatever is
spoken to it, which is why typing Chinese at an English profile gets an English
answer to a correctly heard Chinese question.

## Voices

Text to speech is Edge TTS, which is free and needs no key. The full list is
long. A useful subset:

| Voice | Sounds like |
|---|---|
| `en-US-AvaNeural` | warm, young, the default |
| `en-US-EmmaNeural` | brighter and faster |
| `en-GB-SoniaNeural` | British, calmer |
| `en-US-AndrewNeural` | male, low |
| `en-IN-NeerjaNeural` | Indian English |
| `es-MX-DaliaNeural` | Mexican Spanish |
| `hi-IN-SwaraNeural` | Hindi |
| `ja-JP-NanamiNeural` | Japanese |

Everything available: `docker exec cat-server edge-tts --list-voices`

## Abilities

Two separate systems, and they are easy to confuse.

**The cat's own body.** These tools live on the cat. It sends the server a list
of them when it connects, and the server hands that list to the model. No
profile configures this. If the cat is connected, they work.

The list comes from the firmware and varies by board. The cat on this desk
announces ten: device status, speaker volume, screen brightness, screen theme,
timer management, three for online music, a message inbox, and a pairing code
this setup never uses. Four more are server side and always there:
`handle_exit_intent`, `get_lunar`, and the two the `claude-voice` profile's MCP
server adds. The full list for whatever cat is connected is printed at
`当前支持的函数列表` in `.\cat.ps1 logs`.

`self_timer_manage` is the useful surprise in that list. Timers work today with
nothing added on this side.

**Everything else** comes from MCP servers listed in the profile's `mcp.json`,
in the standard `mcpServers` shape. stdio, SSE and streamable HTTP all work.

The plugin folder baked into the server image is switched off in `base.yaml` and
should stay off. All five bundled plugins are either China-only services or need
a key nobody here has, so turning one on means the model is told it can do
something it will then fail at, out loud, mid-sentence.

## rituals.yaml

The one file in this folder the container never reads. `tools/rituals.py`, a
daemon on the Windows side started with `.\cat.ps1 rituals`, reads it directly,
so editing it needs no rebuild and no restart. The daemon notices the change
and reloads within about a minute. A retry window that is already open keeps
its old settings; the new config applies from the next ritual on.
[docs/speaking-first.md](../docs/speaking-first.md) explains the daemon itself.

The top level:

| Field | Means |
|---|---|
| `bridge` | where the push bridge answers, `http://127.0.0.1:8004` on this machine |
| `model` | the OpenAI model that turns each prompt into the spoken line |
| `retry_minutes` | how long to wait between attempts when no cat is connected |
| `give_up_minutes` | how long to keep trying before recording the ritual as missed |
| `post_repo` | the repo the `post_check` ritual inspects for a commit made today |
| `feeds` | the RSS or Atom feeds the `news` ritual pulls headlines from |

Each entry under `rituals`:

| Field | Means |
|---|---|
| `time` | local wall clock, `"HH:MM"`, quoted so the colon survives |
| `enabled` | `false` skips the ritual without deleting it |
| `prompt` | what the model is asked, and its answer is what the cat says. Words in curly braces are filled in by the daemon first, and each ritual's comment in the file says which ones it gets |
| `on_done` | `post_check` only. `skip` stays quiet when today's commit exists, `congratulate` speaks `done_prompt` instead |
| `done_prompt` | `post_check` only, the prompt used when `on_done` is `congratulate` |

The file is read by a small parser inside the daemon rather than a real YAML
library, because the Windows Python has none installed. It handles exactly the
constructs already in the file: two space indents, quoted and plain values,
dash lists, and folded blocks marked with `>`. Stick to those when editing.

## The cat's face

The screen is drawn by the cat's own firmware and can only show one of 21 built
in faces. Arbitrary images cannot be pushed to it without reflashing. The server
picks a face by sending an emoji, and these are the only ones that map:

`😂 funny` `😭 crying` `😠 angry` `😔 sad` `😍 loving` `😲 surprised`
`😱 shocked` `🤔 thinking` `😌 relaxed` `😴 sleepy` `😜 silly` `🙄 confused`
`😶 neutral` `🙂 happy` `😆 laughing` `😳 embarrassed` `😉 winking`
`😎 cool` `🤤 delicious` `😘 kissy` `😏 confident`

Anything else in a reply leaves the face on `happy`.
