#!/usr/bin/env python3
"""Reads what your Claude Code sessions are doing and serves it over HTTP.

Runs on Windows, because that is where the sessions are. The cat's server runs
in a container inside WSL and reaches this at 127.0.0.1:8765, which works
because the machine runs mirrored networking.

It only reads two things Claude Code and ccpet already write for themselves:

    ~/.claude/sessions/<pid>.json                 name, cwd, busy or idle
    %LOCALAPPDATA%/ccpet/sessions/<id>.json       what the turn is doing

It reads no credentials, sends nothing anywhere, and cannot steer a session.
Talking back to a session is a separate problem, and docs/voice-into-claude.md
explains why it is not solved here.

    py -3.13 tools\\claude_status_agent.py

    GET /status     one spoken sentence plus the structured detail
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765

BUSY = {"thinking", "reading", "editing", "searching", "running", "delegating"}
STALE_AFTER = {"running": 240, "thinking": 120, "delegating": 120}
DEFAULT_STALE = 90
RANK = {"waiting": 4, "error": 4, "done": 2, "asleep": 1}


def alive(pid):
    try:
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:
        return False


def registry():
    out = {}
    d = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        except Exception:
            continue
        pid = doc.get("pid")
        if pid and alive(pid):
            out[int(pid)] = doc
    return out


def pet_states():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return {}
    d = os.path.join(base, "ccpet", "sessions")
    if not os.path.isdir(d):
        return {}
    now = int(time.time())
    out = {}
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        except Exception:
            continue
        state = str(doc.get("state", "")).lower()
        ts = int(doc.get("ts", now))
        pid = int(doc.get("pid", 0))
        if not state:
            continue
        if state in BUSY and now - ts > STALE_AFTER.get(state, DEFAULT_STALE):
            continue
        out[pid] = {"state": state, "ts": ts, "cwd": doc.get("cwd")}
    return out


def snapshot():
    reg = registry()
    pets = pet_states()
    sessions = []
    for pid, doc in reg.items():
        pet = pets.get(pid, {})
        sessions.append({
            "name": doc.get("name") or f"pid-{pid}",
            "project": os.path.basename(doc.get("cwd") or "") or None,
            "status": doc.get("status", "unknown"),
            "doing": pet.get("state"),
            "since": pet.get("ts"),
        })
    sessions.sort(key=lambda s: (-RANK.get(s.get("doing") or "", 3), s["name"]))
    return sessions


def spoken(sessions):
    """One sentence, written to be heard rather than read."""
    if not sessions:
        return "Nothing is running."

    waiting = [s for s in sessions if s["doing"] == "waiting"]
    failed = [s for s in sessions if s["doing"] == "error"]
    busy = [s for s in sessions if s["doing"] in BUSY]
    done = [s for s in sessions if s["doing"] == "done"]

    if waiting:
        names = " and ".join(s["project"] or s["name"] for s in waiting[:2])
        return f"{names} is waiting for you to approve something."
    if failed:
        names = " and ".join(s["project"] or s["name"] for s in failed[:2])
        return f"Something failed in {names}."
    if busy:
        if len(busy) == 1:
            s = busy[0]
            return f"{s['project'] or s['name']} is still working."
        return f"{len(busy)} sessions are still working."
    if done:
        names = " and ".join(s["project"] or s["name"] for s in done[:2])
        return f"{names} finished and is waiting for you."
    return f"{len(sessions)} sessions are open and none of them are busy."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.rstrip("/") != "/status":
            body = {"error": "no such path"}
            code = 404
        else:
            s = snapshot()
            body = {"spoken": spoken(s), "sessions": s}
            code = 200
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    if "--once" in sys.argv:
        s = snapshot()
        print(json.dumps({"spoken": spoken(s), "sessions": s}, indent=2))
        return
    print(f"claude status agent on http://127.0.0.1:{PORT}/status")
    print(f"  {spoken(snapshot())}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
