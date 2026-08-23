#!/usr/bin/env python3
"""Talks to the push bridge, so you can drive the cat from a terminal.

The bridge only exists while a cat is connected, real or fake. Start the fake
one first if the hardware is off:

    python3 tools/fake_cat.py --listen

Then:

    python3 tools/push.py devices
    python3 tools/push.py face thinking
    python3 tools/push.py say "your build finished"
    python3 tools/push.py faces          list every face the firmware has
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8004"

# The only faces the cat's firmware can draw. Names are what the server calls
# them, the emoji is what actually goes down the wire.
FACES = {
    "funny": "\U0001F602", "crying": "\U0001F62D", "angry": "\U0001F620",
    "sad": "\U0001F614", "loving": "\U0001F60D", "surprised": "\U0001F632",
    "shocked": "\U0001F631", "thinking": "\U0001F914", "relaxed": "\U0001F60C",
    "sleepy": "\U0001F634", "silly": "\U0001F61C", "confused": "\U0001F644",
    "neutral": "\U0001F636", "happy": "\U0001F642", "laughing": "\U0001F606",
    "embarrassed": "\U0001F633", "winking": "\U0001F609", "cool": "\U0001F60E",
    "delicious": "\U0001F924", "kissy": "\U0001F618", "confident": "\U0001F60F",
}


def call(path, body=None):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        sys.exit(
            f"the push bridge is not answering on {BASE}.\n"
            f"It only starts once a cat connects. Start the fake one:\n"
            f"    python3 tools/fake_cat.py --listen\n({e})"
        )


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]

    if cmd == "faces":
        for name, emoji in FACES.items():
            print(f"  {emoji}  {name}")
        return
    if cmd == "devices":
        print(json.dumps(call("/devices"), indent=2))
        return
    if cmd == "face":
        if len(args) < 2:
            sys.exit("which face? Try: python3 tools/push.py faces")
        name = args[1]
        emoji = FACES.get(name, name)
        print(json.dumps(call("/face", {"emoji": emoji}), indent=2, ensure_ascii=False))
        return
    if cmd == "say":
        if len(args) < 2:
            sys.exit("say what?")
        print(json.dumps(call("/say", {"text": " ".join(args[1:])}), indent=2))
        return
    sys.exit(f"unknown command {cmd!r}. Try devices, face, say or faces.")


if __name__ == "__main__":
    main()
