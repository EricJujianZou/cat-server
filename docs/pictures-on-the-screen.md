# Pictures on the screen

What it would take to put your own artwork on the cat's face instead of the 21
faces the firmware ships with, what the risk is, and which parts are already
answered.

## Where this stood before

The server's only screen channel was an emoji. It sends one, the firmware maps
it to one of 21 built in faces, and nothing else reaches the display. That is
still what happens in normal operation, and it is why
[ccpet-on-the-cat.md](ccpet-on-the-cat.md) maps ccpet's states to faces rather
than sending its drawings.

## What changed

The cat on this desk reports itself over MCP as `echoear-v2` version `2.0.4.4`.
That is the v2 firmware line, and the open source firmware it is built on
carries a second set of tools the device does not offer the model. In
`main/mcp_server.cc` they are registered with `AddUserOnlyTool`, which stamps
each one `annotations: {audience: ["user"]}` and drops it from the list unless
the asker passes `with_user_tools`. The server never passes it, so these have
been invisible on this setup the whole time.

Two of them matter here.

| Tool | What it does |
|---|---|
| `self.screen.preview_image` | Takes a URL, downloads the image over HTTP, and draws it on the screen |
| `self.assets.set_download_url` | Takes a URL to an assets bundle. The device downloads it on the next boot and applies it, including a whole custom `emoji_collection` |

Both travel down the WebSocket the cat already holds open to this server. The
push bridge in `patches/push_bridge.py` already has a `POST /raw` route that
sends arbitrary JSON down that socket, so nothing new has to be built to reach
them. No USB cable, no reflashing, no vendor account.

The assets partition is 2MB on an 8MB board and 8MB on a 16MB one. It holds
fonts, sound effects, wake word models, background images and the emoji set,
and the firmware refuses a bundle whose checksum does not match.

## What is not yet known

This cat runs a vendor build, not the open source one. It announces four tools
the open source firmware does not have, all of them the seller's online music
and messaging service, so the two builds have diverged. Whether the vendor kept
`preview_image` and `set_download_url` is not something to guess at.

`preview_image` in particular is compiled in only when `CONFIG_LV_USE_SNAPSHOT`
and LVGL are both on. The EchoEar has a round 360 by 360 touch display and may
be built against the emote engine rather than LVGL, in which case that whole
block is absent.

## How to find out

```powershell
.\cat.ps1 talk                    # or just say something to the cat
wsl python3 tools/probe_screen.py
```

The probe asks the cat for its tool list with `with_user_tools` set and prints
what comes back, marking which tools were hidden. It changes nothing on the
device. The cat has to be connected while it runs, and it hangs up a few
minutes after a conversation ends, so wake it first.

Once the probe has run, the hidden tools also show up on the dashboard's
abilities section, under "hidden from the model".

If `preview_image` is there:

```powershell
wsl python3 tools/probe_screen.py --show http://192.168.4.46:8003/whatever.png
```

The URL has to be reachable from the cat, which means the LAN address rather
than localhost.

## Risk

**The probe: none.** Listing tools is a read. The worst case is that the
firmware ignores the flag and answers with the same ten tools.

**`preview_image`: low.** It allocates a buffer the size of the image and draws
it. A file too large for the free heap throws inside the firmware and the tool
call returns an error. Keep images small and sized to the display. The face
comes back on the next thing the cat says.

**`set_download_url`: medium, and the only one worth being careful with.** The
device applies the bundle on its next boot and replaces the emoji set with
whatever is in it. A bundle that is malformed fails its checksum and is
rejected, which is the safe failure. A bundle that is well formed but wrong
leaves the cat drawing your mistake until you send a corrected one. That is
still recoverable over wifi, because the next OTA check picks up a new URL, but
a cat that will not boot far enough to check needs the USB cable and esptool.
Do not touch this one until `preview_image` has been tried and works.

**Reflashing, if the probe comes back empty:** EchoEar is one of Espressif's own
boards and is supported in `78/xiaozhi-esp32`, so a custom build is a real
option rather than a research project. The cost is losing the vendor firmware's
extras, which on this cat are the online music service, the timers, the message
queue and the pairing code. The wake word model would have to be rebuilt too.
ESP32 chips have a ROM bootloader that always answers over USB, so a bad flash
is recoverable, but it needs the cable back.

## What this does not solve

The screen is still the firmware's. Even with `preview_image` working, the cat
draws its own face again the moment it speaks or changes emotion, so a picture
pushed this way is a still frame between utterances rather than a display this
server owns. Owning the display means custom firmware.

## Sources

- [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32), `main/mcp_server.cc`,
  `main/assets.cc`, `main/application.cc`
- [partitions/v2/README.md](https://github.com/78/xiaozhi-esp32/blob/main/partitions/v2/README.md)
  for the assets partition sizes
- [Espressif's EchoEar](https://www.cnx-software.com/2025/09/26/espressif-echoear-esp32-s3-voice-controlled-ai-chatbot-with-circular-touchscreen-and-mic-array/)
  for what the board is
