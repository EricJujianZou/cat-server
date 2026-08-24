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
import hashlib
import http.server
import json
import os
import queue
import re
import socket
import socketserver
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

HOST = "127.0.0.1"
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
RELEASED = "连接资源已释放"

# The cat sends one of these every time it opens or closes the microphone, which
# on a real device is constant.
LISTEN_NOISE = re.compile(r"收到listen消息|收到audio|listen消息")

BUFFER_LINES = 2000
REPLAY_LINES = 400


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
            "functions": [],
            "functions_at": None,
            "mcp": {},
        }
        self._pending_mcp = None

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        while True:
            try:
                proc = subprocess.Popen(
                    ["docker", "compose", "logs", "-f", "--no-color",
                     "--tail", str(REPLAY_LINES)],
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

    def _derive(self, msg, stamp=""):
        at = stamp.split(" ")[-1] if stamp else time.strftime("%H:%M:%S")
        m = RE_HEADERS.search(msg)
        if m:
            ip, blob = m.group(1), m.group(2)
            try:
                headers = ast.literal_eval(blob)
            except (ValueError, SyntaxError):
                headers = {}
            self.state["device"] = {
                "device_id": headers.get("device-id", "unknown"),
                "client_id": headers.get("client-id", ""),
                "ip": ip,
                "host": headers.get("host", ""),
                "agent": headers.get("user-agent", ""),
                "at": at,
            }
            self.state["connected"] = True
            return
        if RELEASED in msg:
            self.state["connected"] = False
            return
        m = RE_FUNCS.search(msg)
        if m:
            try:
                self.state["functions"] = list(ast.literal_eval(m.group(1)))
                self.state["functions_at"] = at
            except (ValueError, SyntaxError):
                pass
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
        try:
            with urllib.request.urlopen(BRIDGE_URL, timeout=2) as r:
                bridge_devices = json.loads(r.read().decode()).get("devices", [])
        except Exception:
            bridge_devices = None

        st = LOGS.state
        connected = st["connected"]
        if bridge_devices is not None:
            connected = len(bridge_devices) > 0

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
            "helpers": helpers,
            "device": st["device"],
            "connected": connected,
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
        voices.append({
            "name": name,
            "gender": gender,
            "categories": categories,
            "personalities": personalities,
            "code": code,
            "locale": locale,
            "language": LANGUAGES.get(code, code),
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
                _voice_cache["voices"] = json.load(open(disk, encoding="utf-8"))
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
        self.send_json({"saved": f["id"],
                        "note": "the server reads data/, so rebuild to make this live"})

    def rebuild(self):
        body = self.read_json()
        name = body.get("profile") or active_profile()
        if name not in list_profiles():
            return self.send_json({"error": f"no profile called {name!r}"}, 400)
        code, out, err = run(
            [sys.executable, os.path.join(ROOT, "tools", "build_profile.py"),
             "use", name], timeout=180)
        self.send_json({"ok": code == 0, "profile": name,
                        "output": (out + err).strip()})

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
            "servers": servers,
            "plugins": bundled_plugins(),
        })

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
        language = LANGUAGES.get(code)
        if not language:
            return self.send_json(
                {"error": f"the dashboard does not know what language {code!r} is, "
                          "so it will not guess at the language line"}, 400)
        path, err = set_voice(profile, voice, language)
        if err:
            return self.send_json({"error": err}, 400)
        self.send_json({
            "ok": True, "profile": profile, "voice": voice, "language": language,
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
    s = socket.socket()
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    url = f"http://{HOST}:{PORT}/"
    if not port_free(HOST, PORT):
        sys.exit(f"something is already listening on {HOST}:{PORT}")
    os.makedirs(CACHE, exist_ok=True)
    LOGS.start()
    STATUS.start()
    httpd = Server((HOST, PORT), Handler)
    print(f"cat dashboard on {url}")
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
