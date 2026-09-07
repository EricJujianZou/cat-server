#!/usr/bin/env python3
"""A local dashboard for the cat server.

Runs inside WSL, binds 127.0.0.1:8080, and serves one page that shows what the
server is doing right now: whether the container is up, the log as it happens,
the files under config/, which tools the model can actually call, and every
Edge TTS voice with a play button.

    python3 tools/dashboard/server.py            start it and open a browser
    python3 tools/dashboard/server.py --no-open  start it and do not

From PowerShell the same thing is `.\\cat.ps1 dash`.

It never reads .env or data/.config.yaml. Both hold live API keys, so the config
browser only ever touches config/, where the values are still ${PLACEHOLDERS}.
"""

import ast
import asyncio
import calendar
import hashlib
import http.server
import json
import os
import queue
import re
import socket
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(ROOT, "config")
PROFILES = os.path.join(CONFIG, "profiles")
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(HERE, ".cache")

# tools/ holds the builder, this folder holds the settings form's two helpers.
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import build_profile as bp        # noqa: E402
import settings_api               # noqa: E402

# The fake cat that .\cat.ps1 talk and the test box both connect as. It shares
# the real handler, so without this it registers on the push bridge and the
# dashboard announces that a cat is connected when only the test rig is.
FAKE_DEVICE_ID = "aa:bb:cc:dd:ee:ff"

# Bound wide so a phone on the same network can open the page. The browser on
# this machine still gets the loopback URL. There is no login on this page,
# which is acceptable on a home network the same way the push bridge is.
HOST = "0.0.0.0"
LOCAL_URL_HOST = "127.0.0.1"
PORT = 8080

# 8000 and 8003 are the server's own, 8004 is the push bridge from patches/.
OTA_URL = "http://127.0.0.1:8003/xiaozhi/ota/"
BRIDGE_URL = "http://127.0.0.1:8004/devices"

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is missing. This runs inside WSL, where it is installed.")


# ---------------------------------------------------------------- log reading

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
# docker compose prefixes every line with the service name and a pipe
COMPOSE_PREFIX = re.compile(r"^[A-Za-z0-9_.-]+\s+\|\s?")
# 260824 09:25:13[0.9.6_00000000000000][core.connection]-INFO-message
LOGLINE = re.compile(
    r"^(\d{6} \d{2}:\d{2}:\d{2})\[([^\]]*)\]\[([^\]]*)\]-([A-Z]+)-(.*)$", re.S
)

RE_HEADERS = re.compile(r"([0-9a-fA-F:.]+) conn - Headers: (\{.*\})\s*$")
RE_FUNCS = re.compile(r"当前支持的函数列表:\s*(\[.*\])\s*$")
RE_MCP_INIT = re.compile(r"初始化服务端MCP客户端:\s*(\S+)")
RE_MCP_UP = re.compile(r"服务端MCP客户端已连接，可用工具:\s*(\[.*\])\s*$")
RE_MCP_DOWN = re.compile(r"服务端MCP客户端已关闭:\s*(\S+)")
# The cat answers tools/list with a full description for every tool it owns.
# The server then logs only the names, so the descriptions are read out of the
# raw message instead. This is where "what does self_timer_manage actually do"
# comes from, rather than from a table in the README that can drift.
RE_MCP_MSG = re.compile(r"收到mcp消息[:：]\s*(\{.*\})\s*$")
RELEASED = "连接资源已释放"

# The cat sends one of these every time it opens or closes the microphone, which
# on a real device is constant.
LISTEN_NOISE = re.compile(r"收到listen消息|收到audio|listen消息")

BUFFER_LINES = 2000
REPLAY_LINES = 400
# How far back to read when the stream opens. A real cat sends a listen
# heartbeat every time it opens its microphone, so the line announcing which
# tools it owns scrolls out of a few hundred lines within one conversation.
# Reading deeper is what stops the dashboard claiming nothing has ever
# connected on a desk where the cat has been talking all morning.
DERIVE_LINES = 6000


def stamp_epoch(stamp):
    """`260824 15:59:15` from the container log into a unix time.

    The container and the host share a clock and a timezone, so this compares
    against time.time() directly. Returns None for the continuation lines that
    carry no stamp of their own.
    """
    try:
        return time.mktime(time.strptime(stamp, "%y%m%d %H:%M:%S"))
    except (ValueError, TypeError):
        return None


class LogHub:
    """One `docker compose logs -f` for the whole process.

    Every browser tab reads from the same stream instead of starting its own,
    and the header state is derived as lines arrive rather than by re-reading
    the log on every poll.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.buffer = []
        self.subscribers = []
        self.seq = 0
        self.alive = False
        self.state = {
            "device": None,
            "connected": False,
            # The cat does not hold the socket open. It dials in when it is
            # woken and hangs up when the conversation ends, so "not connected"
            # is the normal resting state of a cat that is switched on and
            # working. These two carry the times that tell the difference.
            "opened_at": None,
            "closed_at": None,
            "test_device": None,
            "functions": [],
            "functions_at": None,
            "mcp": {},
            # tool name -> one line of what it does, straight off the device
            "tool_docs": {},
            # Tools the firmware marks audience:["user"]. They are hidden from
            # the model on purpose and only appear once something asks with
            # with_user_tools, which tools/probe_screen.py does.
            "user_tools": {},
            "firmware": None,
        }
        self._pending_mcp = None
        self._last_open_was_real = True

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while True:
            try:
                proc = subprocess.Popen(
                    ["docker", "compose", "logs", "-f", "--no-color",
                     "--tail", str(DERIVE_LINES)],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError:
                self._emit_system("docker is not on the path in here")
                time.sleep(10)
                continue
            self.alive = True
            for raw in proc.stdout:
                self._ingest(raw.decode("utf-8", "replace").rstrip("\r\n"))
            self.alive = False
            proc.wait()
            self._emit_system("log stream ended, reconnecting in three seconds")
            time.sleep(3)

    def _emit_system(self, text):
        self._publish({
            "t": time.strftime("%y%m%d %H:%M:%S"),
            "level": "WARNING",
            "module": "dashboard",
            "session": "",
            "msg": text,
            "listen": False,
        })

    def _ingest(self, line):
        line = ANSI.sub("", line)
        line = COMPOSE_PREFIX.sub("", line)
        if not line.strip():
            return
        m = LOGLINE.match(line)
        if m:
            stamp, session, module, level, msg = m.groups()
        else:
            # continuation lines and the odd message from a library that does
            # not use loguru
            stamp, session, module, level, msg = "", "", "", "INFO", line
        entry = {
            "t": stamp,
            "level": level,
            "module": module,
            "session": session,
            "msg": msg,
            "listen": bool(LISTEN_NOISE.search(msg)),
        }
        self._derive(msg, stamp)
        self._publish(entry)

    def _publish(self, entry):
        with self.lock:
            self.seq += 1
            entry["i"] = self.seq
            self.buffer.append(entry)
            if len(self.buffer) > BUFFER_LINES:
                del self.buffer[: len(self.buffer) - BUFFER_LINES]
            dead = []
            for q in self.subscribers:
                try:
                    q.put_nowait(entry)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self.subscribers.remove(q)

    def _derive(self, msg, stamp=""):  # noqa: C901
        at = stamp.split(" ")[-1] if stamp else time.strftime("%H:%M:%S")
        m = RE_HEADERS.search(msg)
        if m:
            ip, blob = m.group(1), m.group(2)
            try:
                headers = ast.literal_eval(blob)
            except (ValueError, SyntaxError):
                headers = {}
            device_id = headers.get("device-id", "unknown")
            if device_id == FAKE_DEVICE_ID:
                # The test box and cat.ps1 talk both dial in as this. Letting
                # it overwrite the record would replace the real cat's identity
                # on the status bar every time a change is tested.
                self.state["test_device"] = {"ip": ip, "at": at}
                self._last_open_was_real = False
                return
            self.state["device"] = {
                "device_id": device_id,
                "client_id": headers.get("client-id", ""),
                "ip": ip,
                "host": headers.get("host", ""),
                "agent": headers.get("user-agent", ""),
                "at": at,
            }
            self.state["connected"] = True
            self.state["opened_at"] = stamp_epoch(stamp) or time.time()
            self._last_open_was_real = True
            return
        if RELEASED in msg:
            # The release line carries no device id, so it is attributed to
            # whoever opened last. Without this a test from the dashboard would
            # move "last spoke" on the real cat.
            if not self._last_open_was_real:
                return
            self.state["connected"] = False
            self.state["closed_at"] = stamp_epoch(stamp) or time.time()
            return
        m = RE_FUNCS.search(msg)
        if m:
            try:
                self.state["functions"] = list(ast.literal_eval(m.group(1)))
                self.state["functions_at"] = at
            except (ValueError, SyntaxError):
                pass
            return
        m = RE_MCP_MSG.search(msg)
        if m:
            self._read_device_mcp(m.group(1))
            return
        m = RE_MCP_INIT.search(msg)
        if m:
            self._pending_mcp = m.group(1)
            return
        m = RE_MCP_UP.search(msg)
        if m:
            try:
                tools = list(ast.literal_eval(m.group(1)))
            except (ValueError, SyntaxError):
                tools = []
            name = self._pending_mcp or "unnamed"
            self.state["mcp"][name] = {
                "connected": True,
                "tools": tools,
                "at": at,
            }
            return
        m = RE_MCP_DOWN.search(msg)
        if m:
            name = m.group(1)
            rec = self.state["mcp"].setdefault(name, {"tools": []})
            rec["connected"] = False
            rec["at"] = at

    def _read_device_mcp(self, blob):
        """Pull tool descriptions and the firmware name out of the cat's own
        MCP replies. Anything unexpected in here is ignored on purpose: this is
        a nicety on top of the name list, never a reason to drop a log line."""
        try:
            payload = json.loads(blob).get("payload") or {}
            result = payload.get("result") or {}
        except (ValueError, AttributeError):
            return
        info = result.get("serverInfo")
        if isinstance(info, dict) and info.get("name"):
            self.state["firmware"] = {
                "name": info.get("name", ""),
                "version": info.get("version", ""),
            }
        tools = result.get("tools")
        if not isinstance(tools, list):
            return
        for tool in tools:
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            # The server renames self.foo.bar to self_foo_bar before it hands
            # the list to the model, so key on the renamed form.
            key = tool["name"].replace(".", "_")
            text = (tool.get("description") or "").strip()
            first = text.splitlines()[0].strip() if text else ""
            if len(first) > 150:
                first = first[:147].rstrip() + "..."
            self.state["tool_docs"][key] = first
            audience = ((tool.get("annotations") or {}).get("audience")) or []
            if "user" in audience:
                self.state["user_tools"][key] = first

    def subscribe(self):
        q = queue.Queue(maxsize=4000)
        with self.lock:
            backlog = list(self.buffer)
            self.subscribers.append(q)
        return q, backlog

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


LOGS = LogHub()


# -------------------------------------------------------------------- helpers

def run(args, timeout=15, cwd=ROOT):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return (r.returncode,
            r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def http_code(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def active_profile():
    path = os.path.join(DATA, ".active-profile")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read().strip() or None
    return None


def list_profiles():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(
        d for d in os.listdir(PROFILES)
        if os.path.isfile(os.path.join(PROFILES, d, "profile.yaml"))
    )


def load_yaml(path):
    """config/ only. Nothing here holds a key, the values are ${PLACEHOLDERS}."""
    try:
        return yaml.safe_load(open(path, encoding="utf-8")) or {}
    except Exception:
        return {}


def merged_tts(profile):
    """What the built profile actually sends to Edge TTS."""
    base = load_yaml(os.path.join(CONFIG, "base.yaml")).get("TTS", {}).get("EdgeTTS", {})
    over = {}
    if profile:
        over = load_yaml(
            os.path.join(PROFILES, profile, "profile.yaml")
        ).get("TTS", {}).get("EdgeTTS", {})
    out = dict(base)
    out.update(over)
    return out


def container_started():
    """When the running container last came up, as a unix time."""
    code, out, _ = run(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", "cat-server"], timeout=10)
    if code != 0 or not out.strip():
        return None
    text = out.strip().split(".")[0].rstrip("Z")
    try:
        # Docker reports this in UTC. timegm reads a UTC struct as UTC;
        # mktime would read it as local and land an hour out under DST.
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def build_state():
    """Whether what is under config/ is what the container is running.

    Three separate facts, because they fail separately: the source can be ahead
    of the last build, and a build can be ahead of the last container start.
    Both are computed from a hash of config/ against the stamp the builder
    writes, so an unchanged rebuild does not read as drift the way an mtime
    comparison would.
    """
    profile = active_profile()
    stamp = bp.read_stamp()
    started = container_started()
    now_hash = bp.source_hash(profile) if profile else ""
    built_hash = stamp.get("hash", "")
    built_at = stamp.get("at")
    # A build from before the stamp existed leaves data/ populated and the
    # stamp empty. That is not the same as never having built, so it says
    # "unknown" and waits for the next rebuild rather than raising an alarm.
    built_before_stamps = not built_hash and os.path.exists(
        os.path.join(DATA, ".config.yaml"))
    return {
        "profile": profile,
        "built_profile": stamp.get("profile"),
        "edited": bool(profile) and bool(built_hash) and now_hash != built_hash,
        "never_built": bool(profile) and not built_hash and not built_before_stamps,
        "unknown": bool(built_before_stamps),
        "profile_switched": bool(stamp.get("profile")) and stamp["profile"] != profile,
        "stale_container": bool(built_at and started and started < built_at - 2),
        "built_at": built_at,
        "started_at": started,
    }


# ------------------------------------------------------------ status polling

class Status:
    """Polled in the background so a browser request never waits on docker."""

    def __init__(self):
        self.lock = threading.Lock()
        self.data = {"ready": False}

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        helpers = {}
        tick = 0
        while True:
            try:
                if tick % 3 == 0:
                    helpers = windows_helpers()
                snap = self._collect(helpers)
                with self.lock:
                    self.data = snap
            except Exception as exc:  # a dashboard that dies is worse than a stale one
                with self.lock:
                    self.data = {"ready": True, "error": str(exc)}
            tick += 1
            time.sleep(3)

    def _collect(self, helpers):
        code, out, _ = run(
            ["docker", "ps", "--filter", "name=cat-server",
             "--format", "{{.Status}}"], timeout=10)
        container = out.strip() if code == 0 else ""

        profile = active_profile()
        desc = ""
        if profile:
            desc = load_yaml(
                os.path.join(PROFILES, profile, "profile.yaml")
            ).get("description", "")

        bridge_devices = None
        test_devices = []
        try:
            with urllib.request.urlopen(BRIDGE_URL, timeout=2) as r:
                all_devices = json.loads(r.read().decode()).get("devices", [])
            test_devices = [d for d in all_devices if d == FAKE_DEVICE_ID]
            bridge_devices = [d for d in all_devices if d != FAKE_DEVICE_ID]
        except Exception:
            bridge_devices = None

        st = LOGS.state
        connected = st["connected"]
        if bridge_devices is not None:
            # The push bridge holds the live socket registry, so it beats the
            # log whenever it answers.
            connected = len(bridge_devices) > 0

        # talking: a socket is open this second.
        # idle:    it has dialled in before and hung up, which is the resting
        #          state of a cat that is switched on and working fine.
        # never:   nothing has reached the server since it started.
        last = max(x for x in [st["opened_at"] or 0, st["closed_at"] or 0])
        if connected:
            link = "talking"
        elif st["device"]:
            link = "idle"
        else:
            link = "never"
        since = int(time.time() - last) if last else None

        tts = merged_tts(profile)
        return {
            "ready": True,
            "container": container,
            "container_up": container.lower().startswith("up"),
            "profile": profile,
            "description": desc,
            "profiles": list_profiles(),
            "ota": http_code(OTA_URL),
            "bridge": bridge_devices,
            "test_cat": bool(test_devices),
            "build": build_state(),
            "helpers": helpers,
            "device": st["device"],
            "connected": connected,
            "link": link,
            "since": since,
            "voice": tts.get("voice", ""),
            "language": tts.get("language", ""),
            "log_stream": LOGS.alive,
            "at": time.strftime("%H:%M:%S"),
        }

    def get(self):
        with self.lock:
            return dict(self.data)


HELPERS = [
    {"needle": "claude_status_agent", "label": "status agent",
     "what": "answers what Claude is doing"},
    {"needle": "claude_watch", "label": "face watcher",
     "what": "puts session state on the cat face"},
]

PS_QUERY = (
    "(Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" "
    "| Select-Object -ExpandProperty CommandLine) -join [char]10"
)


def windows_helpers():
    """The two helpers run on Windows, so ask Windows through WSL interop."""
    code, out, _ = run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PS_QUERY],
        timeout=20, cwd="/")
    if code != 0:
        return {h["needle"]: {"state": "unknown", "label": h["label"],
                              "what": h["what"]} for h in HELPERS}
    lines = out.replace("\r", "")
    return {
        h["needle"]: {
            "state": "running" if h["needle"] in lines else "stopped",
            "label": h["label"],
            "what": h["what"],
        }
        for h in HELPERS
    }


STATUS = Status()


# ------------------------------------------------------------- the test box

# The one exchange the dashboard runs to answer "did that change work".
#
# It dials the server exactly the way the cat does, sends the text the cat's
# speech recognition would have produced, and reports what came back: the
# sentences, the face, and every tool the model called with its arguments.
# Tool calls are the only way a tool toggle can be checked at all, and nothing
# else in this dashboard shows them.
#
# The audio comes back as Opus frames, which this does not decode. It counts
# them, which proves synthesis ran. To actually hear the profile's voice the
# page re-synthesises the reply text through /api/tts, and says so, because
# that is not the audio the cat produced.

TALK_URL = "ws://127.0.0.1:8000/xiaozhi/v1/"


def talk_once(text, wait=30.0):
    return asyncio.run(_talk(text, max(5.0, min(wait, 90.0))))


async def _talk(text, wait):
    import uuid
    try:
        import websockets
    except ImportError:
        return {"error": "the websockets package is missing in here. "
                         "pip3 install websockets"}
    try:
        from fake_cat import DEVICE_TOOLS
    except ImportError:
        DEVICE_TOOLS = []

    started = time.time()
    out = {"said": [], "face": None, "body": [], "frames": 0, "bytes": 0,
           "other": [], "error": None}

    headers = {"device-id": FAKE_DEVICE_ID, "client-id": str(uuid.uuid4()),
               "protocol-version": "1"}
    try:
        ws = await asyncio.wait_for(
            websockets.connect(TALK_URL, additional_headers=headers, max_size=None),
            timeout=8)
    except Exception as exc:
        return {"error": "could not reach the server on 8000: " + str(exc)}

    async def send(obj):
        await ws.send(json.dumps(obj, ensure_ascii=False))

    try:
        await send({"type": "hello", "version": 1, "transport": "websocket",
                    "features": {"mcp": True},
                    "audio_params": {"format": "opus", "sample_rate": 16000,
                                     "channels": 1, "frame_duration": 60}})
        asked = False
        quiet_until = None
        deadline = started + wait
        while time.time() < deadline:
            left = deadline - time.time()
            if quiet_until:
                left = min(left, max(0.05, quiet_until - time.time()))
                if time.time() >= quiet_until:
                    break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, left))
            except asyncio.TimeoutError:
                if quiet_until:
                    break
                continue
            if isinstance(raw, bytes):
                out["frames"] += 1
                out["bytes"] += len(raw)
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("type")
            if kind == "hello":
                await send({"type": "mcp", "payload": {
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05",
                               "capabilities": {"tools": {}},
                               "clientInfo": {"name": "cat-dash", "version": "1"}}}})
                if not asked:
                    asked = True
                    await asyncio.sleep(0.6)
                    await send({"type": "listen", "mode": "manual",
                                "state": "detect", "text": text, "source": "text"})
            elif kind == "llm":
                out["face"] = {"emoji": msg.get("text", ""),
                               "emotion": msg.get("emotion", "")}
            elif kind == "tts":
                state = msg.get("state")
                if state == "sentence_start" and msg.get("text"):
                    out["said"].append(msg["text"])
                    quiet_until = None
                elif state == "stop" and out["said"]:
                    # More sentences often follow, so hold briefly rather than
                    # cutting the reply off at the first full stop.
                    quiet_until = time.time() + 1.8
            elif kind == "mcp":
                payload = msg.get("payload") or {}
                method = payload.get("method")
                if method == "tools/list":
                    await send({"type": "mcp", "payload": {
                        "jsonrpc": "2.0", "id": payload.get("id"),
                        "result": {"tools": DEVICE_TOOLS}}})
                elif method == "tools/call":
                    params = payload.get("params") or {}
                    out["body"].append({"name": params.get("name", ""),
                                        "args": params.get("arguments") or {}})
                    await send({"type": "mcp", "payload": {
                        "jsonrpc": "2.0", "id": payload.get("id"),
                        "result": {"content": [{"type": "text", "text": "ok"}],
                                   "isError": False}}})
            elif kind == "goodbye":
                break
            elif kind not in ("stt", "listen"):
                out["other"].append(kind or "?")
    finally:
        try:
            await ws.close()
        except Exception:
            pass

    out["seconds"] = round(time.time() - started, 1)
    if not out["said"] and not out["error"]:
        out["error"] = ("nothing came back within " + str(int(wait)) +
                        " seconds. The container may still be starting.")
    return out


# ----------------------------------------------------------------- progress

# The ledger behind the progress tab. The companion MCP server inside the
# container writes it when the owner talks, and the daemon that speaks the
# scheduled prompts writes its own rows into the same table. This side only
# ever reads: query_only is set on every connection, and the existence check
# in progress_payload keeps a plain connect from creating an empty file.
# A missing file just means nothing has been logged yet.
COMPANION_DB = os.path.join(DATA, "companion.db")


def companion_rows(path):
    # Not mode=ro: the ledger is in WAL mode on a Windows mount, and a
    # read-only connection cannot set up the WAL shared memory there, which
    # surfaces as "disk I/O error". query_only keeps the no-writes guarantee.
    conn = sqlite3.connect(path, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        return conn.execute(
            "SELECT ts, kind, text, data FROM log ORDER BY id").fetchall()
    finally:
        conn.close()


def progress_payload(path=COMPANION_DB):
    """Everything the progress tab renders, in one payload."""
    if not os.path.exists(path):
        return {"exists": False}
    try:
        rows = companion_rows(path)
    except sqlite3.Error as exc:
        return {"exists": True, "error": str(exc)}

    def blob(raw):
        try:
            doc = json.loads(raw)
            return doc if isinstance(doc, dict) else {}
        except ValueError:
            return {}

    weights, ideas, focus, days = [], [], [], {}
    cutoff_30 = time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - 29 * 86400))
    completions = []
    for ts, kind, text, raw in rows:
        day = ts[:10]
        data = blob(raw)
        if kind == "weight" and isinstance(data.get("kg"), (int, float)):
            weights.append({"ts": ts, "day": day, "kg": data["kg"]})
        elif kind == "idea":
            ideas.append({"ts": ts, "day": day, "text": text})
        elif kind == "focus":
            focus.append({
                "ts": ts, "day": day, "intent": text,
                "minutes": data.get("minutes"),
                "open": bool(data.get("open")),
                "completed": bool(data.get("completed")),
                "outcome": data.get("outcome", ""),
            })
        elif kind in ("plan", "outcome", "missed"):
            rec = days.setdefault(day, {
                "day": day, "plan": "", "outcome": "",
                "completion": None, "missed": []})
            if kind == "plan":
                rec["plan"] = (rec["plan"] + " / " + text).strip(" /")
            elif kind == "outcome":
                rec["outcome"] = (rec["outcome"] + " / " + text).strip(" /")
                if isinstance(data.get("completion"), (int, float)):
                    rec["completion"] = data["completion"]
                    if day >= cutoff_30:
                        completions.append(data["completion"])
            else:
                rec["missed"].append(text)

    rate = None
    if completions:
        rate = {"avg": sum(completions) / len(completions),
                "count": len(completions)}
    return {
        "exists": True,
        "weights": weights,
        "days": sorted(days.values(), key=lambda r: r["day"], reverse=True)[:30],
        "rate30": rate,
        "focus": list(reversed(focus))[:30],
        "ideas": list(reversed(ideas))[:100],
    }


# ----------------------------------------------------------------- shopping

# The shopping list, in its own table in the same ledger file. The voice tools
# in tools/mcp/companion_mcp.py write it when the owner talks to the cat, and
# this page is the second writer. Same rules as every other opener of this
# file: no WAL, short connections.
SHOPPING_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS shopping ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "text TEXT NOT NULL, "
    "added_at TEXT NOT NULL, "
    "bought INTEGER NOT NULL DEFAULT 0)"
)


def shopping_conn():
    conn = sqlite3.connect(COMPANION_DB, timeout=5)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(SHOPPING_SCHEMA)
    return conn


def shopping_payload():
    try:
        conn = shopping_conn()
        try:
            rows = conn.execute(
                "SELECT id, text, added_at, bought FROM shopping "
                "ORDER BY bought, id").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"error": str(exc)}
    return {"items": [
        {"id": rid, "text": text, "added_at": ts, "bought": bool(b)}
        for rid, text, ts, b in rows
    ]}


def shopping_change(body):
    """One write per request, then the fresh list, so the page always repaints
    from what is actually in the file rather than what it hoped happened."""
    op = body.get("op", "")
    try:
        conn = shopping_conn()
        try:
            with conn:
                if op == "add":
                    text = " ".join(str(body.get("text") or "").split())
                    if not text:
                        return {"error": "type an item first"}
                    if len(text) > 200:
                        return {"error": "keep an item under 200 characters"}
                    dup = conn.execute(
                        "SELECT 1 FROM shopping WHERE bought=0 AND lower(text)=?",
                        (text.lower(),)).fetchone()
                    if not dup:
                        conn.execute(
                            "INSERT INTO shopping (text, added_at) VALUES (?, ?)",
                            (text, time.strftime("%Y-%m-%d %H:%M:%S")))
                elif op == "bought":
                    conn.execute(
                        "UPDATE shopping SET bought=? WHERE id=?",
                        (1 if body.get("bought") else 0, int(body.get("id", 0))))
                elif op == "clear":
                    conn.execute("DELETE FROM shopping WHERE bought=1")
                else:
                    return {"error": "no such op"}
        finally:
            conn.close()
    except (sqlite3.Error, TypeError, ValueError) as exc:
        return {"error": str(exc)}
    return shopping_payload()


# ----------------------------------------------------------------- rituals

# What the cat says on its own. The daemon (tools/rituals.py, started with
# .\cat.ps1 rituals) reads config/rituals.yaml twice a minute and rewrites
# data/.rituals-heartbeat on every tick, so a heartbeat younger than three
# ticks means it is running. Nothing in the container is involved: an edit to
# the file needs no rebuild, the daemon just picks it up.
RITUALS_YAML = os.path.join(CONFIG, "rituals.yaml")
RITUALS_HEARTBEAT = os.path.join(DATA, ".rituals-heartbeat")


def rituals_payload():
    doc = load_yaml(RITUALS_YAML)
    rows = []
    for name, rec in (doc.get("rituals") or {}).items():
        if not isinstance(rec, dict):
            continue
        prompt = " ".join(str(rec.get("prompt", "")).split())
        if len(prompt) > 110:
            prompt = prompt[:107].rstrip() + "..."
        rows.append({
            "name": name,
            "time": str(rec.get("time", "")),
            "enabled": bool(rec.get("enabled", True)),
            "what": prompt,
        })
    age, running, poll = None, False, 30
    try:
        hb = json.load(open(RITUALS_HEARTBEAT, encoding="utf-8"))
        poll = int(hb.get("poll_seconds") or 30)
        age = int(time.time() - time.mktime(
            time.strptime(hb.get("ts", ""), "%Y-%m-%dT%H:%M:%S")))
        running = age < 90
    except (OSError, ValueError, TypeError, OverflowError):
        pass
    return {
        "file": "config/rituals.yaml",
        "list": rows,
        "daemon": {"running": running, "age": age, "poll": poll},
    }


# ------------------------------------------------------------- config browser

# An explicit whitelist. The client sends an id from this map and nothing else,
# so no path it can send reaches .env or data/.config.yaml.
def config_files():
    files = [{
        "id": "base.yaml",
        "path": os.path.join(CONFIG, "base.yaml"),
        "label": "base.yaml",
        "group": "shared",
        "kind": "yaml",
    }]
    if os.path.exists(RITUALS_YAML):
        files.append({
            "id": "rituals.yaml",
            "path": RITUALS_YAML,
            "label": "rituals.yaml",
            "group": "shared",
            "kind": "yaml",
        })
    for name in list_profiles():
        for fname, kind in (("profile.yaml", "yaml"),
                            ("prompt.md", "markdown"),
                            ("mcp.json", "json")):
            p = os.path.join(PROFILES, name, fname)
            if os.path.exists(p):
                files.append({
                    "id": f"profiles/{name}/{fname}",
                    "path": p,
                    "label": fname,
                    "group": name,
                    "kind": kind,
                })
    return files


def config_lookup(file_id):
    for f in config_files():
        if f["id"] == file_id:
            return f
    return None


PLUGIN_COMMENT = re.compile(r"^#\s{2,}([a-z_]+)\s{2,}(.+?)\s*$")


# The four tools that are never announced by the cat, so nothing upstream
# describes them. Short lines, because the abilities list is scanned not read.
SERVER_TOOL_DOCS = {
    "handle_exit_intent": "Lets the model end the conversation itself, in any "
                          "language, without matching a phrase.",
    "get_lunar": "Answers lunar calendar questions.",
    "claude_status": "What Claude Code is doing right now.",
    "claude_sessions": "Which Claude Code sessions are open.",
}


def bundled_plugins():
    """The five plugins in the image, with the reason each one is off taken
    from the comment block in base.yaml rather than repeated here."""
    out = []
    try:
        text = open(os.path.join(CONFIG, "base.yaml"), encoding="utf-8").read()
    except OSError:
        return out
    for line in text.splitlines():
        m = PLUGIN_COMMENT.match(line)
        if m:
            out.append({"name": m.group(1), "reason": m.group(2)})
    return out


# ------------------------------------------------------------------- voices

VOICE_NAME = re.compile(r"^[a-z]{2,3}(-[A-Za-z]+)+Neural$|^[a-z]{2,3}-[A-Za-z0-9-]+$")

LANGUAGES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "az": "Azerbaijani",
    "bg": "Bulgarian", "bn": "Bengali", "bs": "Bosnian", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fil": "Filipino", "fr": "French",
    "ga": "Irish", "gl": "Galician", "gu": "Gujarati", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
    "is": "Icelandic", "it": "Italian", "iu": "Inuktitut", "ja": "Japanese",
    "jv": "Javanese", "ka": "Georgian", "kk": "Kazakh", "km": "Khmer",
    "kn": "Kannada", "ko": "Korean", "lo": "Lao", "lt": "Lithuanian",
    "lv": "Latvian", "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian",
    "mr": "Marathi", "ms": "Malay", "mt": "Maltese", "my": "Burmese",
    "nb": "Norwegian", "ne": "Nepali", "nl": "Dutch", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali",
    "sq": "Albanian", "sr": "Serbian", "su": "Sundanese", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek",
    "vi": "Vietnamese", "zh": "Chinese", "zu": "Zulu",
}

# Some locales are not accents of one language, they are different languages
# that are written differently. zh-HK is the one that matters here: a Cantonese
# voice reading Mandarin-written Chinese mispronounces the grammar, not just the
# accent. The value on the left is what goes into the profile's `language` line,
# which the server drops verbatim into "You MUST write EVERY response in X", so
# it has to be a name a model will actually write differently for.
LOCALE_LANGUAGES = {
    "zh-CN": ("Mandarin Chinese", "simplified characters"),
    "zh-TW": ("Traditional Chinese", "Taiwan, traditional characters"),
    "zh-HK": ("Cantonese", "Hong Kong, traditional characters"),
    "yue-CN": ("Cantonese", "simplified characters"),
    "pt-BR": ("Brazilian Portuguese", ""),
    "pt-PT": ("European Portuguese", ""),
    "es-ES": ("European Spanish", ""),
    "fr-CA": ("Canadian French", ""),
}

# Accent-only splits inside one written language. These keep the language name
# and only carry a note, because the model should write the same words either
# way and only the voice changes.
REGION_NOTES = {
    "zh-CN-liaoning": "northeastern accent",
    "zh-CN-shaanxi": "Shaanxi accent",
}


def language_family(name):
    """Every language name that is a fair description of what this voice speaks.

    A zh-CN voice is honestly called Chinese or Mandarin Chinese, so a profile
    that says either is fine and there is nothing to warn about. A profile that
    says Chinese next to an English voice is a real mistake, and that is the
    only case worth interrupting for.
    """
    parts = name.split("-")
    code = parts[0]
    out = {LANGUAGES.get(code, code), voice_language(name)[0]}
    for locale, (lang, _note) in LOCALE_LANGUAGES.items():
        if locale.split("-")[0] == code:
            out.add(lang)
    return {x for x in out if x}


def voice_language(name):
    """(what goes in the profile's language line, a short note for the list).

    Falls back to the plain language name for every locale that is only an
    accent, which is nearly all of them.
    """
    parts = name.split("-")
    locale = "-".join(parts[:2])
    region = "-".join(parts[:3]) if len(parts) > 3 else ""
    if region in REGION_NOTES:
        lang, note = LOCALE_LANGUAGES.get(locale, (LANGUAGES.get(parts[0], parts[0]), ""))
        return lang, REGION_NOTES[region]
    if locale in LOCALE_LANGUAGES:
        return LOCALE_LANGUAGES[locale]
    return LANGUAGES.get(parts[0], parts[0]), ""

# Bumped whenever a voice record grows or changes a field, so a cache written
# by an older dashboard is thrown out instead of quietly used.
VOICE_SCHEMA = 2

_voice_cache = {"at": 0, "voices": [], "error": ""}
_voice_lock = threading.Lock()


def parse_voice_table(text):
    """edge-tts prints a fixed width table. The dashes under the header give
    the column edges, which is steadier than splitting on runs of spaces."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return []
    rule = None
    for i, ln in enumerate(lines):
        if set(ln.replace(" ", "")) == {"-"}:
            rule = i
            break
    if rule is None:
        return []
    spans = []
    start = None
    for i, ch in enumerate(lines[rule] + " "):
        if ch == "-" and start is None:
            start = i
        elif ch != "-" and start is not None:
            spans.append((start, i))
            start = None
    voices = []
    for ln in lines[rule + 1:]:
        cells = [ln[a:b].strip() for a, b in spans]
        while len(cells) < 4:
            cells.append("")
        name, gender, categories, personalities = cells[:4]
        if not name or "-" not in name:
            continue
        parts = name.split("-")
        code = parts[0]
        locale = "-".join(parts[:2])
        language, note = voice_language(name)
        voices.append({
            "name": name,
            "gender": gender,
            "categories": categories,
            "personalities": personalities,
            "code": code,
            "locale": locale,
            "language": language,
            "family": LANGUAGES.get(code, code),
            "note": note,
            "v": VOICE_SCHEMA,
            "short": parts[-1].replace("Neural", "") if len(parts) > 2 else name,
        })
    return voices


def load_voices(refresh=False):
    with _voice_lock:
        if not refresh and _voice_cache["voices"]:
            return _voice_cache
        disk = os.path.join(CACHE, "voices.json")
        if not refresh and os.path.exists(disk):
            try:
                cached = json.load(open(disk, encoding="utf-8"))
                # A cache written by an older build would put every Chinese
                # voice back under one label, so it is thrown away rather than
                # trusted. Re-reading costs one docker exec.
                if cached and cached[0].get("v") != VOICE_SCHEMA:
                    cached = []
                _voice_cache["voices"] = cached
                _voice_cache["at"] = os.path.getmtime(disk)
                if _voice_cache["voices"]:
                    return _voice_cache
            except Exception:
                pass
        code, out, err = run(
            ["docker", "exec", "cat-server", "edge-tts", "--list-voices"],
            timeout=90)
        if code != 0:
            _voice_cache["error"] = (err or out).strip()[:400] or "edge-tts failed"
            return _voice_cache
        voices = parse_voice_table(out)
        _voice_cache["voices"] = voices
        _voice_cache["error"] = "" if voices else "could not parse the voice table"
        _voice_cache["at"] = time.time()
        os.makedirs(CACHE, exist_ok=True)
        try:
            with open(disk, "w", encoding="utf-8") as f:
                json.dump(voices, f)
        except OSError:
            pass
        return _voice_cache


def voice_exists(name):
    return any(v["name"] == name for v in load_voices()["voices"])


def synthesise(voice, text):
    """Render one sample through the container's edge-tts and keep the mp3.

    The arguments go straight to docker exec as a list, never through a shell,
    and the voice is checked against the list before we get here.
    """
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha256(("\x00".join([voice, text])).encode("utf-8")).hexdigest()[:24]
    path = os.path.join(CACHE, key + ".mp3")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path, None
    inside = "/tmp/dash-" + key + ".mp3"
    code, out, err = run(
        ["docker", "exec", "cat-server", "edge-tts",
         "--voice", voice, "--text", text, "--write-media", inside],
        timeout=90)
    if code != 0:
        detail = (err or out).strip()
        if "NoAudioReceived" in detail:
            return None, ("Edge TTS sent back nothing for this voice and this text. "
                          "It does that when the text is entirely in a language the "
                          "voice does not speak, so add a few words the voice can "
                          "read and try again.")
        return None, detail[:400] or "edge-tts failed"
    try:
        r = subprocess.run(
            ["docker", "exec", "cat-server", "cat", inside],
            cwd=ROOT, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "timed out reading the mp3 out of the container"
    if r.returncode != 0 or not r.stdout:
        return None, "the container produced no audio"
    with open(path, "wb") as f:
        f.write(r.stdout)
    run(["docker", "exec", "cat-server", "rm", "-f", inside], timeout=20)
    return path, None


# ------------------------------------------------- writing a voice to a profile

def set_voice(profile, voice, language):
    """Put voice and language into the profile's TTS: EdgeTTS: block.

    This edits the text rather than round-tripping the YAML, because the
    profiles carry comments that explain themselves and a safe_dump would
    throw all of them away.
    """
    path = os.path.join(PROFILES, profile, "profile.yaml")
    if not os.path.isfile(path):
        return None, f"no profile.yaml for {profile!r}"
    lines = open(path, encoding="utf-8").read().split("\n")

    def indent_of(s):
        return len(s) - len(s.lstrip(" "))

    def find_key(start, end, key, want_indent=None):
        for i in range(start, end):
            s = lines[i]
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            ind = indent_of(s)
            if want_indent is not None and ind != want_indent:
                continue
            if s.strip().split(":")[0].strip() == key:
                return i
        return -1

    def block_end(start, parent_indent):
        for i in range(start + 1, len(lines)):
            s = lines[i]
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            if indent_of(s) <= parent_indent:
                return i
        return len(lines)

    tts = find_key(0, len(lines), "TTS", 0)
    if tts == -1:
        block = ["", "TTS:", "  EdgeTTS:", f"    voice: {voice}",
                 f"    language: {language}"]
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(block + [""])
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        return path, None

    tts_end = block_end(tts, 0)
    edge = find_key(tts + 1, tts_end, "EdgeTTS")
    if edge == -1:
        lines.insert(tts + 1, "  EdgeTTS:")
        lines.insert(tts + 2, f"    voice: {voice}")
        lines.insert(tts + 3, f"    language: {language}")
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        return path, None

    edge_indent = indent_of(lines[edge])
    edge_end = block_end(edge, edge_indent)
    child = None
    for i in range(edge + 1, edge_end):
        if lines[i].strip() and not lines[i].lstrip().startswith("#"):
            child = indent_of(lines[i])
            break
    if child is None or child <= edge_indent:
        child = edge_indent + 2

    v = find_key(edge + 1, edge_end, "voice", child)
    if v == -1:
        lines.insert(edge + 1, " " * child + f"voice: {voice}")
        v = edge + 1
        edge_end += 1
    else:
        lines[v] = " " * child + f"voice: {voice}"

    lang = find_key(edge + 1, edge_end, "language", child)
    if lang == -1:
        lines.insert(v + 1, " " * child + f"language: {language}")
    else:
        lines[lang] = " " * child + f"language: {language}"

    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    return path, None


# --------------------------------------------------------------------- server

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "cat-dash"

    def log_message(self, fmt, *args):
        pass  # the page has its own log pane, this one just gets in the way

    # -- plumbing

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if n <= 0 or n > 4_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    # -- routes

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                return self.serve_page()
            if path == "/api/status":
                return self.send_json(STATUS.get())
            if path == "/api/logs":
                return self.serve_logs()
            if path == "/api/config":
                return self.send_json({
                    "files": [{k: v for k, v in f.items() if k != "path"}
                              for f in config_files()],
                    "profile": active_profile(),
                })
            if path == "/api/config/file":
                return self.serve_config_file(q.get("id", [""])[0])
            if path == "/api/abilities":
                return self.serve_abilities()
            if path == "/api/voices":
                return self.serve_voices("1" in q.get("refresh", []))
            if path == "/api/tts":
                return self.serve_tts(q)
            if path == "/api/settings":
                return self.serve_settings()
            if path == "/api/progress":
                return self.send_json(progress_payload())
            if path == "/api/shopping":
                return self.send_json(shopping_payload())
            if path == "/favicon.ico":
                # Browsers ask for this unprompted. Answering keeps a 404 out
                # of the console of a page whose whole job is showing faults.
                return self.send_bytes(b"", "image/x-icon", 204)
        except (BrokenPipeError, ConnectionResetError):
            return
        self.send_json({"error": "no such route"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/config/file":
                return self.save_config_file()
            if path == "/api/rebuild":
                return self.rebuild()
            if path == "/api/voice":
                return self.apply_voice()
            if path == "/api/settings":
                return self.save_setting()
            if path == "/api/talk":
                return self.serve_talk()
            if path == "/api/shopping":
                return self.send_json(shopping_change(self.read_json()))
        except (BrokenPipeError, ConnectionResetError):
            return
        self.send_json({"error": "no such route"}, 404)

    # -- the page

    def serve_page(self):
        path = os.path.join(HERE, "index.html")
        try:
            body = open(path, "rb").read()
        except OSError:
            return self.send_json({"error": "index.html is missing"}, 500)
        self.send_bytes(body, "text/html; charset=utf-8",
                        extra={"Cache-Control": "no-store"})

    # -- logs

    def serve_logs(self):
        q, backlog = LOGS.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for entry in backlog[-REPLAY_LINES:]:
                self.wfile.write(self._sse(entry))
            self.wfile.flush()
            while True:
                try:
                    entry = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(self._sse(entry))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            LOGS.unsubscribe(q)

    @staticmethod
    def _sse(entry):
        return ("data: " + json.dumps(entry, ensure_ascii=False) + "\n\n").encode("utf-8")

    # -- config

    def serve_config_file(self, file_id):
        f = config_lookup(file_id)
        if not f:
            return self.send_json({"error": "not a config file"}, 400)
        try:
            text = open(f["path"], encoding="utf-8").read()
        except OSError as exc:
            return self.send_json({"error": str(exc)}, 500)
        self.send_json({"id": f["id"], "kind": f["kind"], "text": text,
                        "label": f["label"], "group": f["group"]})

    def save_config_file(self):
        body = self.read_json()
        f = config_lookup(body.get("id", ""))
        if not f:
            return self.send_json({"error": "not a config file"}, 400)
        text = body.get("text")
        if not isinstance(text, str):
            return self.send_json({"error": "no text"}, 400)
        if f["kind"] == "yaml":
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as exc:
                return self.send_json({"error": "that is not valid yaml: "
                                       + str(exc)[:300]}, 400)
        if f["kind"] == "json":
            try:
                json.loads(text)
            except ValueError as exc:
                return self.send_json({"error": "that is not valid json: "
                                       + str(exc)[:300]}, 400)
        try:
            with open(f["path"], "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            return self.send_json({"error": str(exc)}, 500)
        note = ("the rituals daemon rereads this file within a minute"
                if f["id"] == "rituals.yaml"
                else "the server reads data/, so rebuild to make this live")
        self.send_json({"saved": f["id"], "note": note})

    def rebuild(self):
        body = self.read_json()
        name = body.get("profile") or active_profile()
        if name not in list_profiles():
            return self.send_json({"error": f"no profile called {name!r}"}, 400)
        code, out, err = run(
            [sys.executable, os.path.join(ROOT, "tools", "build_profile.py"),
             "use", name], timeout=180)
        text = (out + err).strip()
        # The builder now exits non-zero on a failed restart, but a stale copy
        # of it would not, so the output is checked as well. A rebuild that
        # says "done" while the container is on the old build is the one lie
        # this dashboard must never tell.
        ok = code == 0 and "restart failed" not in text.lower()
        self.send_json({"ok": ok, "profile": name, "output": text})

    # -- abilities

    def serve_abilities(self):
        profile = active_profile()
        mcp_conf = {}
        if profile:
            p = os.path.join(PROFILES, profile, "mcp.json")
            if os.path.exists(p):
                try:
                    mcp_conf = json.load(open(p, encoding="utf-8")).get("mcpServers", {})
                except ValueError:
                    mcp_conf = {}
        live = LOGS.state["mcp"]
        servers = []
        for name, spec in sorted(mcp_conf.items()):
            if "command" in spec:
                transport = "stdio"
                target = " ".join([spec.get("command", "")] + list(spec.get("args", [])))
            elif "url" in spec:
                transport = spec.get("type", "http")
                target = spec.get("url", "")
            else:
                transport = "unknown"
                target = ""
            seen = live.get(name, {})
            servers.append({
                "name": name,
                "transport": transport,
                "target": target,
                "state": ("connected" if seen.get("connected")
                          else "closed" if seen else "not seen in the log"),
                "tools": seen.get("tools", []),
                "at": seen.get("at", ""),
            })
        self.send_json({
            "profile": profile,
            "functions": LOGS.state["functions"],
            "functions_at": LOGS.state["functions_at"],
            "docs": dict(SERVER_TOOL_DOCS, **LOGS.state["tool_docs"]),
            "user_tools": LOGS.state["user_tools"],
            "firmware": LOGS.state["firmware"],
            "servers": servers,
            "plugins": bundled_plugins(),
        })

    # -- settings

    def serve_settings(self):
        profile = active_profile()
        profiles = [{"name": n, "description": load_yaml(
            os.path.join(PROFILES, n, "profile.yaml")).get("description", "")}
            for n in list_profiles()]
        payload = settings_api.view(profile, profiles, LOGS.state)
        payload["rituals"] = rituals_payload()
        self.send_json(payload)

    def save_setting(self):
        body = self.read_json()
        field = body.get("field", "")
        profile = body.get("profile") or active_profile()
        # Ritual fields write config/rituals.yaml, which belongs to no profile.
        if not field.startswith("ritual_") and profile not in list_profiles():
            return self.send_json({"error": "no profile is built yet"}, 400)
        try:
            written, err = settings_api.apply(profile, field, body.get("value"))
        except Exception as exc:  # a bad edit must not take the dashboard down
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        if err:
            return self.send_json({"error": err}, 400)
        self.send_json({"ok": True, "field": field, "file": written})

    # -- the test box

    def serve_talk(self):
        body = self.read_json()
        text = (body.get("text") or "").strip()
        if not text:
            return self.send_json({"error": "type something to say first"}, 400)
        if len(text) > 500:
            return self.send_json({"error": "keep it under 500 characters"}, 400)
        try:
            result = talk_once(text, float(body.get("wait") or 30))
        except Exception as exc:
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 502)
        self.send_json(result)

    # -- voices

    def serve_voices(self, refresh):
        cache = load_voices(refresh)
        profile = active_profile()
        tts = merged_tts(profile)
        self.send_json({
            "voices": cache["voices"],
            "error": cache["error"],
            "current": tts.get("voice", ""),
            "language": tts.get("language", ""),
            "profile": profile,
        })

    def serve_tts(self, q):
        voice = (q.get("voice", [""])[0] or "").strip()
        text = (q.get("text", [""])[0] or "").strip()
        if not voice or not text:
            return self.send_json({"error": "voice and text are both needed"}, 400)
        if len(text) > 400:
            return self.send_json({"error": "keep the sample under 400 characters"}, 400)
        if not voice_exists(voice):
            return self.send_json({"error": f"no voice called {voice!r}"}, 400)
        path, err = synthesise(voice, text)
        if err:
            return self.send_json({"error": err}, 502)
        body = open(path, "rb").read()
        self.send_bytes(body, "audio/mpeg", extra={"Cache-Control": "no-store"})

    def apply_voice(self):
        body = self.read_json()
        voice = (body.get("voice") or "").strip()
        profile = body.get("profile") or active_profile()
        if profile not in list_profiles():
            return self.send_json({"error": "no profile is built yet"}, 400)
        if not voice_exists(voice):
            return self.send_json({"error": f"no voice called {voice!r}"}, 400)
        code = voice.split("-")[0]
        if code not in LANGUAGES and "-".join(voice.split("-")[:2]) not in LOCALE_LANGUAGES:
            return self.send_json(
                {"error": f"the dashboard does not know what language {code!r} is, "
                          "so it will not guess at the language line"}, 400)
        language, note = voice_language(voice)
        path, err = set_voice(profile, voice, language)
        if err:
            return self.send_json({"error": err}, 400)
        self.send_json({
            "ok": True, "profile": profile, "voice": voice, "language": language,
            "note": note,
            "file": os.path.relpath(path, ROOT).replace("\\", "/"),
        })


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def open_browser(url):
    """WSL can reach the Windows shell, which is where the browser is."""
    for cmd in (["powershell.exe", "-NoProfile", "-Command", "Start-Process", url],
                ["explorer.exe", url],
                ["xdg-open", url]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, cwd="/")
            return True
        except FileNotFoundError:
            continue
    return False


def port_free(host, port):
    """Whether the dashboard can bind here.

    SO_REUSEADDR is set for the same reason the server sets it: a socket left
    in TIME_WAIT by the previous run would otherwise refuse the next one for a
    minute or two, and restarting right after ctrl-c is the normal thing to do.
    """
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def lan_ip():
    """The address a phone on the same network would dial. WSL mirrored
    networking means this is the Windows adapter's own address. No packet is
    sent: connect() on UDP only picks the route."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main():
    port = PORT
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            sys.exit("--port needs a number")
    url = f"http://{LOCAL_URL_HOST}:{port}/"
    if not port_free(HOST, port):
        sys.exit(f"something is already listening on port {port}")
    os.makedirs(CACHE, exist_ok=True)
    LOGS.start()
    STATUS.start()
    httpd = Server((HOST, port), Handler)
    print(f"cat dashboard on {url}")
    ip = lan_ip()
    if ip:
        print(f"phones on this network: http://{ip}:{port}/")
    print("ctrl-c to stop")
    if "--no-open" not in sys.argv:
        open_browser(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
