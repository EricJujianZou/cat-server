#!/usr/bin/env python3
"""The named settings behind the dashboard's Cat tab.

Everything here reads from and writes to `config/`, never to `data/`, so no
code path in this file can reach a live API key. Writes go through edit_yaml so
the comments in the profiles survive, because those comments are the only place
that records why a Chinese voice and a Chinese language line have to move
together.

Each field reports where its value came from: the profile, base.yaml, or the
image's own config.yaml, which is the one the dashboard cannot edit. Saying
"inherited from the image" is the point. Without it a value that cannot be
changed here looks the same as one that can, and there is nothing to tell you
when to stop looking for the knob.
"""

import json
import os
import re
import subprocess
import time

import edit_yaml as ey

try:
    import yaml
except ImportError:  # pragma: no cover - the dashboard already refuses to start
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(ROOT, "config")
PROFILES = os.path.join(CONFIG, "profiles")

# Models worth offering. The list is short on purpose: anything else can be
# typed into profile.yaml directly, and a stale dropdown of forty names is
# worse than four correct ones.
MODELS = [
    ("gpt-4o-mini", "cheap and quick, the default"),
    ("gpt-4o", "better at following a persona, costs more"),
    ("gpt-4.1-mini", "newer small model"),
    ("gpt-4.1", "newer full model"),
]

# Read out of the image so the form can show what a value falls back to when
# nothing under config/ sets it. Cached, because it costs a docker exec.
_image = {"at": 0, "conf": None}
IMAGE_CONF_PATH = "/opt/xiaozhi-esp32-server/config.yaml"


def image_defaults():
    if _image["conf"] is not None and time.time() - _image["at"] < 300:
        return _image["conf"]
    conf = {}
    try:
        r = subprocess.run(
            ["docker", "exec", "cat-server", "cat", IMAGE_CONF_PATH],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and yaml:
            conf = yaml.safe_load(r.stdout) or {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        conf = {}
    _image["conf"] = conf
    _image["at"] = time.time()
    return conf


def load_yaml(path):
    if not yaml or not os.path.isfile(path):
        return {}
    try:
        return yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def read_text(path):
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def write_text(path, text):
    # Always land on exactly one trailing newline. Replacing the last block in
    # a file otherwise eats the one that was there, and every save after that
    # shows up in git as a whitespace change.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")


def profile_path(profile, name="profile.yaml"):
    return os.path.join(PROFILES, profile, name)


def dig(doc, keypath):
    cur = doc
    for k in keypath:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def resolve(profile, keypath, image_key=None):
    """(value, where it came from) for one setting.

    The profile beats base.yaml, and base.yaml beats whatever the image ships.
    """
    over = load_yaml(profile_path(profile)) if profile else {}
    v = dig(over, keypath)
    if v is not None:
        return v, "profile"
    v = dig(load_yaml(os.path.join(CONFIG, "base.yaml")), keypath)
    if v is not None:
        return v, "base"
    key = image_key or (keypath[-1] if keypath else "")
    v = dig(image_defaults(), [key] if key else [])
    if v is not None:
        return v, "image"
    return None, "unset"


# ------------------------------------------------------------------- reading

def view(profile, profiles, tools_state):
    """Everything the Cat tab renders, in one payload.

    `tools_state` is the live tool list the log hub derived, so the read-only
    section can say what the cat announced rather than what a table claims.
    """
    base_text = read_text(os.path.join(CONFIG, "base.yaml"))
    prof_text = read_text(profile_path(profile)) if profile else ""

    tts, tts_src = resolve(profile, ["TTS", "EdgeTTS", "voice"])
    lang, lang_src = resolve(profile, ["TTS", "EdgeTTS", "language"])
    model, model_src = resolve(profile, ["LLM", "OpenAILLM", "model_name"])
    idle, idle_src = resolve(profile, ["close_connection_no_voice_time"])
    greet, greet_src = resolve(profile, ["enable_greeting"])
    greet_reply, greet_reply_src = resolve(
        profile, ["enable_wakeup_words_response_cache"])
    wake, wake_src = resolve(profile, ["wakeup_words"])
    exits, exit_src = resolve(profile, ["exit_commands"])

    on_plugins = dig(load_yaml(os.path.join(CONFIG, "base.yaml")),
                     ["Intent", "function_call", "functions"]) or []

    return {
        "profile": profile,
        "profiles": profiles,
        "persona": read_text(profile_path(profile, "prompt.md")) if profile else "",
        "description": (load_yaml(profile_path(profile)) or {}).get("description", ""),
        "voice": {"value": tts, "source": tts_src},
        "language": {"value": lang, "source": lang_src,
                     "should_be": expected_language(tts),
                     "mismatch": not language_fits(tts, lang)},
        "model": {"value": model, "source": model_src, "options": MODELS},
        "idle": {"value": idle, "source": idle_src},
        "greeting": {"value": bool(greet), "source": greet_src},
        "greet_reply": {"value": bool(greet_reply), "source": greet_reply_src},
        "wake_words": {"value": wake or [], "source": wake_src},
        "exit_commands": {"value": exits or [], "source": exit_src},
        "plugins": plugin_rows(base_text, on_plugins),
        "mcp": mcp_rows(profile),
        "device_tools": device_tool_rows(tools_state),
        "user_tools": [{"name": n, "doc": d} for n, d in
                       sorted((tools_state.get("user_tools") or {}).items())],
        "walls": walls(tts or ""),
        "files": {
            "base": "config/base.yaml",
            "profile": f"config/profiles/{profile}/profile.yaml" if profile else "",
            "prompt": f"config/profiles/{profile}/prompt.md" if profile else "",
            "mcp": f"config/profiles/{profile}/mcp.json" if profile else "",
        },
        "has_prof_text": bool(prof_text),
    }


def plugin_rows(base_text, enabled):
    """The five bundled plugins, each with the reason it is off read out of
    the comment block in base.yaml rather than repeated here."""
    import re
    pat = re.compile(r"^#\s{3}(\w+)\s{2,}(.+?)\s*$")
    rows = []
    for line in base_text.splitlines():
        m = pat.match(line)
        if m:
            rows.append({
                "name": m.group(1),
                "reason": m.group(2),
                "on": m.group(1) in enabled,
            })
    return rows


def mcp_rows(profile):
    """MCP servers from the profile, including the ones switched off.

    Switching one off moves it into `disabledServers` rather than deleting it,
    so the command line and its arguments survive and turning it back on is
    one click rather than a rewrite.
    """
    if not profile:
        return []
    path = profile_path(profile, "mcp.json")
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for on, key in ((True, "mcpServers"), (False, "disabledServers")):
        for name, spec in sorted((doc.get(key) or {}).items()):
            if "command" in spec:
                transport = "stdio"
                target = " ".join([spec.get("command", "")] + list(spec.get("args", [])))
            elif "url" in spec:
                transport = spec.get("type", "http")
                target = spec.get("url", "")
            else:
                transport = "unknown"
                target = ""
            rows.append({"name": name, "on": on,
                         "transport": transport, "target": target})
    return rows


def device_tool_rows(tools_state):
    """What the cat itself announced, which nothing on this side configures.

    Falls back to every tool the cat has ever described this session, so the
    list does not empty out the moment the cat hangs up.
    """
    docs = tools_state.get("tool_docs") or {}
    names = [n for n in (tools_state.get("functions") or []) if n.startswith("self_")]
    if not names:
        names = sorted(n for n in docs if n.startswith("self_"))
    return [{"name": n, "doc": docs.get(n, "")} for n in names]


def expected_language(voice):
    """The most precise language name for this voice."""
    if not voice:
        return ""
    try:
        import server  # the voice tables live there
        return server.voice_language(voice)[0]
    except Exception:
        return ""


def language_fits(voice, written):
    """Whether the profile's language line describes what this voice speaks.

    Only a genuine mismatch counts, an English voice told to write Chinese.
    Calling a zh-CN voice Chinese rather than Mandarin Chinese is not wrong
    and is not worth a warning.
    """
    if not voice or not written:
        return True
    try:
        import server
        return written in server.language_family(voice)
    except Exception:
        return True


def spoken_greeting(voice):
    """What the cat actually said last time it was woken, if it is cached.

    The server picks one of nine hardcoded Chinese lines and caches the audio
    per voice under data/.wakeup_words.yaml. Reading it back is the only way to
    show the real sentence rather than a guess at it.
    """
    doc = load_yaml(os.path.join(ROOT, "data", ".wakeup_words.yaml"))
    if not isinstance(doc, dict):
        return ""
    for rec in doc.values():
        if isinstance(rec, dict) and rec.get("voice") == voice and rec.get("text"):
            return rec["text"]
    for rec in doc.values():
        if isinstance(rec, dict) and rec.get("text"):
            return rec["text"]
    return ""


def walls(voice=""):
    """Things people look for here and will not find, with where they live.

    An absent setting is indistinguishable from a setting you have not found
    yet, so a search for one has no stopping point. This gives it one.
    """
    return [
        {
            "what": "The wake word itself",
            "where": "the cat's firmware",
            "why": "Your cat wakes on 你好小智. Detection runs on "
                   "the device before any audio reaches this server, so nothing "
                   "here changes it. A different one means training a new model "
                   "on thousands of samples and reflashing over USB.",
            "value": "你好小智  (nǐ hǎo xiǎo zhì)",
        },
        {
            "what": "The wording of the canned greeting",
            "where": "the server image",
            "why": "Nine Chinese lines hardcoded in core/handle/helloHandle.py, "
                   "picked at random. The wording is fixed, but whether it plays "
                   "at all is not: the two switches under How it listens turn it "
                   "off, or hand the greeting to the model so it comes back in "
                   "your own language.",
            "value": spoken_greeting(voice),
        },
        {
            "what": "The face it draws",
            "where": "the cat's firmware",
            "why": "The server sends an emoji and the firmware picks one of "
                   "21 faces it already holds. See the abilities tab for what "
                   "can and cannot reach the screen.",
        },
    ]


# ------------------------------------------------------------------- writing

RITUALS = os.path.join(CONFIG, "rituals.yaml")


def ritual_names():
    doc = load_yaml(RITUALS)
    return [n for n in (doc.get("rituals") or {})]


def apply(profile, field, value):
    """Write one named setting. Returns (changed file, error)."""
    # The two ritual fields come first: they write config/rituals.yaml, which
    # belongs to no profile and needs no rebuild. The daemon rereads the file
    # on its own within a minute.
    if field in ("ritual_enabled", "ritual_time"):
        name = (value or {}).get("name")
        if name not in ritual_names():
            return None, f"no ritual called {name!r} in config/rituals.yaml"
        if field == "ritual_enabled":
            return write_yaml(RITUALS, ["rituals", name, "enabled"],
                              bool((value or {}).get("on")))
        t = str((value or {}).get("time") or "").strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", t)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            return None, "the time has to be HH:MM on a 24 hour clock, like 08:20"
        return write_yaml(RITUALS, ["rituals", name, "time"], t)

    if not profile:
        return None, "no profile is built yet"

    if field == "persona":
        if not isinstance(value, str):
            return None, "the persona has to be text"
        path = profile_path(profile, "prompt.md")
        write_text(path, value.rstrip() + "\n")
        return rel(path), None

    if field == "description":
        return write_yaml(profile_path(profile), ["description"], str(value))

    if field == "model":
        return write_yaml(profile_path(profile),
                          ["LLM", "OpenAILLM", "model_name"], str(value))

    if field == "idle":
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None, "that has to be a whole number of seconds"
        if not 15 <= n <= 3600:
            return None, "keep it between 15 seconds and an hour"
        return write_yaml(os.path.join(CONFIG, "base.yaml"),
                          ["close_connection_no_voice_time"], n)

    if field == "greeting":
        return write_yaml(os.path.join(CONFIG, "base.yaml"),
                          ["enable_greeting"], bool(value))

    if field == "greet_reply":
        return write_yaml(os.path.join(CONFIG, "base.yaml"),
                          ["enable_wakeup_words_response_cache"], bool(value))

    if field in ("wake_words", "exit_commands"):
        if not isinstance(value, list):
            return None, "that field is a list"
        items = [str(x).strip() for x in value if str(x).strip()]
        key = "wakeup_words" if field == "wake_words" else "exit_commands"
        return write_list(os.path.join(CONFIG, "base.yaml"), [key], items)

    if field == "plugin":
        return toggle_plugin(value)

    if field == "mcp":
        return toggle_mcp(profile, value)

    return None, f"nothing called {field!r} is settable"


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def write_yaml(path, keypath, value):
    text = read_text(path)
    if not text:
        return None, f"cannot read {rel(path)}"
    out = ey.set_scalar(text, keypath, value)
    err = check_yaml(out)
    if err:
        return None, err
    write_text(path, out)
    return rel(path), None


def write_list(path, keypath, items):
    text = read_text(path)
    if not text:
        return None, f"cannot read {rel(path)}"
    out = ey.set_list(text, keypath, items)
    err = check_yaml(out)
    if err:
        return None, err
    write_text(path, out)
    return rel(path), None


def check_yaml(text):
    """Never write a file the server would then fail to load."""
    if not yaml:
        return None
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return "that edit would not parse as YAML: " + str(exc).split("\n")[0]
    return None


def toggle_plugin(value):
    name = (value or {}).get("name")
    on = bool((value or {}).get("on"))
    if not name:
        return None, "which plugin?"
    path = os.path.join(CONFIG, "base.yaml")
    text = read_text(path)
    current = dig(load_yaml(path), ["Intent", "function_call", "functions"]) or []
    current = [x for x in current if x != name]
    if on:
        current.append(name)
    return write_list(path, ["Intent", "function_call", "functions"], sorted(current))


def toggle_mcp(profile, value):
    name = (value or {}).get("name")
    on = bool((value or {}).get("on"))
    if not name:
        return None, "which server?"
    path = profile_path(profile, "mcp.json")
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"cannot read {rel(path)}: {exc}"
    live = doc.setdefault("mcpServers", {})
    off = doc.setdefault("disabledServers", {})
    src, dst = (off, live) if on else (live, off)
    if name in src:
        dst[name] = src.pop(name)
    elif name not in dst:
        return None, f"no server called {name!r} in {rel(path)}"
    if not off:
        doc.pop("disabledServers", None)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return rel(path), None
