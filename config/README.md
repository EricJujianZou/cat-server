# config

Everything that decides what the cat is lives in this folder. Nothing outside it
needs editing to change the cat's personality, voice, model or abilities.

```
config/
  base.yaml                shared by every profile. Server ports, providers, keys.
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

**The cat's own body.** Speaker volume, screen brightness and screen theme are
tools that live on the cat. It sends the server a list of them when it connects,
and the server hands that list to the model. No profile configures this. If the
cat is connected, they work.

**Everything else** comes from MCP servers listed in the profile's `mcp.json`,
in the standard `mcpServers` shape. stdio, SSE and streamable HTTP all work.

The plugin folder baked into the server image is switched off in `base.yaml` and
should stay off. All five bundled plugins are either China-only services or need
a key nobody here has, so turning one on means the model is told it can do
something it will then fail at, out loud, mid-sentence.

## The cat's face

The screen is drawn by the cat's own firmware and can only show one of 21 built
in faces. Arbitrary images cannot be pushed to it without reflashing. The server
picks a face by sending an emoji, and these are the only ones that map:

`😂 funny` `😭 crying` `😠 angry` `😔 sad` `😍 loving` `😲 surprised`
`😱 shocked` `🤔 thinking` `😌 relaxed` `😴 sleepy` `😜 silly` `🙄 confused`
`😶 neutral` `🙂 happy` `😆 laughing` `😳 embarrassed` `😉 winking`
`😎 cool` `🤤 delicious` `😘 kissy` `😏 confident`

Anything else in a reply leaves the face on `happy`.
