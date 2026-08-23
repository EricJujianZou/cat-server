#!/usr/bin/env python3
"""Puts your Claude Code session on the cat's face.

ccpet already writes one JSON file per live session and already worked out which
one should win when several are running. This reads the same files, applies the
same rule, and pushes the result to the cat as a face and, for the one state
worth interrupting someone for, a spoken line.

Runs on Windows, because that is where Claude Code and ccpet are. It reaches the
cat at 127.0.0.1:8004, which works because WSL runs in mirrored networking mode.

    python tools\\claude_watch.py            watch and push
    python tools\\claude_watch.py --dry-run  print what it would push
    python tools\\claude_watch.py --say-all  speak on done and error too

ccpet's own artwork does not go on the cat. The cat's screen is drawn by its
firmware and can only show one of 21 built in faces, so this maps the states
onto those. Sound is speech, because ccpet ships no audio files.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BRIDGE = "http://127.0.0.1:8004"
POLL_SECONDS = 2.0

# Windows terminals still default to cp1252, which cannot print an emoji.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ccpet's own vocabulary, from ccpet/src/state.rs
BUSY = {"thinking", "reading", "editing", "searching", "running", "delegating"}
STALE_AFTER = {"running": 240, "thinking": 120, "delegating": 120}
DEFAULT_STALE = 90
WARM_SECONDS = 3600  # matches ccpet's warm_minutes=60

# Louder beats busier. A session reading files must never bury one that is
# blocked waiting for you.
RANK = {"waiting": 4, "error": 4, "done": 2, "asleep": 1}

FACE = {
    "waiting": "\U0001F632",   # surprised, the one worth looking up for
    "error": "\U0001F614",     # sad
    "done": "\U0001F924",      # delicious, ccpet's instant noodles
    "asleep": "\U0001F634",    # sleepy
    "busy": "\U0001F914",      # thinking, the whole busy family
}


def sessions_dir():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        sys.exit("no LOCALAPPDATA, so this is not running on Windows")
    return os.path.join(base, "ccpet", "sessions")


def claude_sessions():
    """Name and cwd per pid, from Claude Code's own registry."""
    out = {}
    home = os.path.expanduser("~")
    d = os.path.join(home, ".claude", "sessions")
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        except Exception:
            continue
        if doc.get("pid"):
            out[int(doc["pid"])] = doc
    return out


def alive(pid):
    if not pid:
        return True
    try:
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:
        return True


def read_state():
    """The one state the cat should show, plus which project it belongs to."""
    d = sessions_dir()
    now = int(time.time())
    if not os.path.isdir(d):
        return "asleep", None, 0

    live = []
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        except Exception:
            continue
        state = str(doc.get("state", "")).lower()
        if not state:
            continue
        ts = int(doc.get("ts", now))
        pid = int(doc.get("pid", 0))
        if pid and not alive(pid):
            continue
        if state in BUSY and now - ts > STALE_AFTER.get(state, DEFAULT_STALE):
            continue
        live.append((state, ts, pid, doc.get("cwd")))

    if not live:
        return "asleep", None, 0

    registry = claude_sessions()

    def key(item):
        state, ts, pid, _ = item
        effective = state
        if state == "done" and now - ts > WARM_SECONDS:
            effective = "asleep"
        rank = RANK.get(effective, 3 if effective in BUSY else 1)
        return (rank, ts, pid)

    state, ts, pid, cwd = max(live, key=key)
    doc = registry.get(pid, {})
    label = doc.get("name") or (os.path.basename(cwd) if cwd else None)
    return state, label, len(live)


def face_for(state):
    if state in BUSY:
        return FACE["busy"]
    return FACE.get(state, FACE["busy"])


def post(path, body, dry_run=False):
    if dry_run:
        print(f"  would POST {path} {body}")
        return True
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BRIDGE + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read()
        return True
    except urllib.error.HTTPError as e:
        if e.code == 503:
            return False  # no cat connected, nothing to shout about
        print(f"  {path} -> {e.code} {e.read()[:120]!r}")
        return False
    except urllib.error.URLError:
        return False


def line_for(state, label):
    where = f" in {label}" if label else ""
    if state == "waiting":
        return f"Claude needs you{where}."
    if state == "error":
        return f"Something failed{where}."
    if state == "done":
        return f"Finished{where}."
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--say-all", action="store_true",
                   help="speak on done and error too, not just waiting")
    p.add_argument("--silent", action="store_true", help="face only, never speak")
    p.add_argument("--once", action="store_true", help="push once and exit")
    args = p.parse_args()

    speak_on = {"waiting"}
    if args.say_all:
        speak_on = {"waiting", "error", "done"}
    if args.silent:
        speak_on = set()

    last_state = None
    print(f"watching ccpet, pushing to {BRIDGE}")
    print(f"speaking on: {', '.join(sorted(speak_on)) or 'nothing'}")
    while True:
        state, label, count = read_state()
        if state != last_state:
            emoji = face_for(state)
            shown = f"{state}{f' ({label})' if label else ''}"
            print(f"{time.strftime('%H:%M:%S')}  {emoji}  {shown}  [{count} live]")
            ok = post("/face", {"emoji": emoji}, args.dry_run)
            if ok and state in speak_on:
                text = line_for(state, label)
                if text:
                    post("/say", {"text": text}, args.dry_run)
            if ok or args.dry_run:
                last_state = state
        if args.once:
            return
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
