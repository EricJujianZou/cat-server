#!/usr/bin/env python3
"""Ask the cat what it can really do with its screen.

The server asks the cat for its tool list the normal way and gets ten back.
The firmware also holds a second set marked `audience: ["user"]`, which it hides
unless the asker sets `with_user_tools`. On the open source v2 firmware that
hidden set includes two things this whole repo would like to have:

    self.screen.preview_image      downloads an image from a URL and draws it
    self.assets.set_download_url   points the device at an emoji pack it
                                   fetches on the next boot

Both go over the WebSocket the cat already holds, so if they are there, custom
artwork on the screen needs no cable and no reflash. Whether this cat has them
depends on the vendor build, and the only way to know is to ask it.

This sends the question through the push bridge on 8004 and prints the answer.
It is read only: listing tools changes nothing on the device.

    python3 tools/probe_screen.py             list every tool, hidden ones too
    python3 tools/probe_screen.py --show URL  try drawing that image on it

The cat has to be connected while this runs. It hangs up a few minutes after a
conversation ends, so wake it first and then run this.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

BRIDGE = "http://127.0.0.1:8004"
PROBE_ID = 90001
SHOW_ID = 90002


def bridge(path, body=None):
    url = BRIDGE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.load(r), None
    except urllib.error.HTTPError as exc:
        try:
            return None, json.load(exc).get("error", str(exc))
        except Exception:
            return None, str(exc)
    except OSError as exc:
        return None, f"the push bridge on 8004 is not answering: {exc}"


def devices():
    doc, err = bridge("/devices")
    if err:
        return [], err
    return doc.get("devices", []), None


def send(message):
    return bridge("/raw", {"message": message})


def read_reply(want_id, seconds=12):
    """Watch the container log for the cat's answer.

    The reply comes back over the cat's own socket, so the server logs it and
    nothing sends it here. Reading the log is the whole receive path.
    """
    pat = re.compile(r"收到mcp消息[:：]\s*(\{.*\})\s*$")
    end = time.time() + seconds
    proc = subprocess.Popen(
        ["docker", "compose", "logs", "-f", "--no-color", "--tail", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while time.time() < end:
            line = proc.stdout.readline()
            if not line:
                break
            m = pat.search(line.decode("utf-8", "replace").rstrip())
            if not m:
                continue
            try:
                doc = json.loads(m.group(1))
            except ValueError:
                continue
            payload = doc.get("payload") or {}
            if payload.get("id") == want_id:
                return payload
    finally:
        proc.kill()
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--show", metavar="URL",
                   help="try drawing this image on the cat's screen")
    p.add_argument("--wait", type=float, default=12,
                   help="seconds to wait for the cat to answer")
    args = p.parse_args()

    live, err = devices()
    if err:
        sys.exit(err)
    if not live:
        sys.exit("no cat is connected. It hangs up between conversations, so "
                 "wake it and run this within the next couple of minutes.")
    print(f"asking {live[0]}")

    _, err = send({"type": "mcp", "payload": {
        "jsonrpc": "2.0", "id": PROBE_ID, "method": "tools/list",
        "params": {"with_user_tools": 1}}})
    if err:
        sys.exit(err)

    reply = read_reply(PROBE_ID, args.wait)
    if reply is None:
        sys.exit("the cat did not answer in time. Either it hung up, or this "
                 "firmware ignores with_user_tools.")

    tools = ((reply.get("result") or {}).get("tools")) or []
    if not tools:
        sys.exit("the cat answered with no tools at all.")

    hidden, plain = [], []
    for t in tools:
        aud = ((t.get("annotations") or {}).get("audience")) or []
        (hidden if "user" in aud else plain).append(t)

    print(f"\n{len(plain)} tools the model can call:")
    for t in plain:
        print("   ", t["name"])

    if hidden:
        print(f"\n{len(hidden)} hidden from the model, callable from here:")
        for t in hidden:
            first = (t.get("description") or "").splitlines()[0][:70]
            print("   ", t["name"], "-", first)
    else:
        print("\nNothing hidden. This build does not carry the user-only set, "
              "so custom artwork means new firmware.")

    names = {t["name"] for t in tools}
    print()
    for name, what in (
        ("self.screen.preview_image", "arbitrary images over wifi, no reflash"),
        ("self.assets.set_download_url", "a whole custom emoji pack, no reflash"),
    ):
        print(("  yes  " if name in names else "  no   ") + name + "  " + what)

    if not args.show:
        return
    if "self.screen.preview_image" not in names:
        sys.exit("\nThis cat has no preview_image, so there is nothing to try.")
    print(f"\ndrawing {args.show}")
    _, err = send({"type": "mcp", "payload": {
        "jsonrpc": "2.0", "id": SHOW_ID, "method": "tools/call",
        "params": {"name": "self.screen.preview_image",
                   "arguments": {"url": args.show}}}})
    if err:
        sys.exit(err)
    reply = read_reply(SHOW_ID, args.wait)
    if reply is None:
        print("no answer. Look at the cat, it may have drawn it anyway.")
    elif reply.get("error"):
        print("it refused:", json.dumps(reply["error"], ensure_ascii=False))
    else:
        print("it accepted:", json.dumps(reply.get("result"), ensure_ascii=False))


if __name__ == "__main__":
    main()
