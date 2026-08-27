#!/usr/bin/env python3
"""The cat speaks first, at fixed times of day and while he sits at the desk.

Reads config/rituals.yaml, builds each spoken line by asking the model, and
pushes it through the bridge on 127.0.0.1:8004. Runs on Windows like the other
helpers, because that is where the sibling repo, the local clock, and the
keyboard the desk reminder watches all are. Start it detached with
.\\cat.ps1 rituals.

    py -3.13 tools\\rituals.py                  run the daemon
    py -3.13 tools\\rituals.py --dry-run        build every enabled line now,
                                                print it, post nothing
    py -3.13 tools\\rituals.py --dry-run news   just that one ritual
    py -3.13 tools\\rituals.py --db some.db     another database, for testing

Every line spoken, and every ritual the cat was not reachable for, is written
to data/companion.db. That is the same file other tools write plans, outcomes
and weights into, and this daemon reads those back as context. If no cat is
connected at ritual time it retries every five minutes for up to forty five,
records the miss, and waits for the next ritual. Nothing a single ritual does
can stop the loop.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date, time as dtime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "rituals.yaml")
DB_PATH = os.path.join(ROOT, "data", "companion.db")
POLL_SECONDS = 30

# Touched every tick so anything else, the dashboard mostly, can tell a
# running daemon from a stopped one by the file's age.
HEARTBEAT_PATH = os.path.join(ROOT, "data", ".rituals-heartbeat")

# Windows terminals still default to cp1252, which cannot print an emoji.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SYSTEM_PROMPT = (
    "You are a small cat shaped speaker on a desk, talking out loud to your "
    "owner. Reply with only the words to say. Plain spoken English, short "
    "sentences, no emoji, no markdown, no stage directions, no dashes."
)

# Spoken when the model cannot be reached, so a dead API key never silences a
# ritual. Plain sentences on purpose, these go out loud.
FALLBACK = {
    "weight": "Please weigh yourself and tell me the number.",
    "morning_plan": "Good morning. What is the plan for today?",
    "news": "I could not put the news together this morning.",
    "afternoon_review": "How did today go? Tell me what you got done.",
    "post_check": "Nothing has been committed to content-machine today. "
                  "The post is five minutes of work.",
    "post_check_done": "You already posted to content-machine today.",
    "look_outside": "You've been at the desk twenty minutes. "
                    "Look out the window for a bit.",
}


# ------------------------------------------------------------------- config

def load_config(path):
    """Reads the subset of YAML that config/rituals.yaml uses.

    The Windows Python has no yaml module and these helpers run with nothing
    installed, so this reads exactly what that file contains: maps nested by
    indent, dash lists of scalars, quoted and plain values, and folded blocks
    marked with >. It is not a YAML parser and does not try to be one.
    """
    lines = []
    for raw in open(path, encoding="utf-8"):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip()), raw.strip()))
    doc, i = _parse_block(lines, 0, 0)
    if i != len(lines):
        raise ValueError(f"{path}: could not read past line {i}")
    return doc


def _parse_block(lines, i, indent):
    if i < len(lines) and lines[i][1].startswith("- "):
        out = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
            out.append(_scalar(lines[i][1][2:]))
            i += 1
        return out, i
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        text = lines[i][1]
        if ":" not in text:
            raise ValueError(f"expected key: value, got {text!r}")
        key, _, rest = text.partition(":")
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest == ">":
            folded = []
            while i < len(lines) and lines[i][0] > indent:
                folded.append(lines[i][1])
                i += 1
            out[key] = " ".join(folded)
        elif rest:
            out[key] = _scalar(rest)
        else:
            child_indent = lines[i][0] if i < len(lines) else indent
            if child_indent <= indent:
                out[key] = None
            else:
                out[key], i = _parse_block(lines, i, child_indent)
    return out, i


def _scalar(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    try:
        return int(s)
    except ValueError:
        return s


def read_env():
    """KEY=value pairs from the repo's .env, same rules as build_profile.py."""
    env = {}
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return env
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ------------------------------------------------------------------ database

# Shared with whatever else writes to companion.db. This daemon writes the
# kinds prompt and missed, and reads plan, outcome and weight for context.
# The schema is fixed, other code depends on it staying exactly this.
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts TEXT NOT NULL, "
    "kind TEXT NOT NULL, "
    "text TEXT NOT NULL DEFAULT '', "
    "data TEXT NOT NULL DEFAULT '{}')"
)


def open_db(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    db = sqlite3.connect(path)
    # Not WAL. This file is shared by a Windows process (this daemon), WSL
    # tools and the container, all through the drive mount, and WAL's shared
    # memory does not work across that boundary: the moment one side holds a
    # WAL connection the others get "disk I/O error". Plain journaling with a
    # busy timeout is fine at a few writes a day.
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA busy_timeout=5000")
    db.execute(SCHEMA)
    db.commit()
    return db


def log_row(db, kind, text, data):
    db.execute(
        "INSERT INTO log (ts, kind, text, data) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), kind, text,
         json.dumps(data, ensure_ascii=False)),
    )
    db.commit()


def texts_on(db, kind, day):
    rows = db.execute(
        "SELECT text FROM log WHERE kind = ? AND ts LIKE ? ORDER BY id",
        (kind, day.isoformat() + "%"),
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def last_of(db, kind):
    """(ts, text) of the newest row of that kind, or None."""
    return db.execute(
        "SELECT ts, text FROM log WHERE kind = ? ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()


def already_ran(db, name, day):
    """Whether this ritual already spoke or was missed today.

    The database is the record, so a daemon restarted at noon does not repeat
    the morning."""
    row = db.execute(
        "SELECT 1 FROM log WHERE kind IN ('prompt', 'missed') "
        "AND data LIKE ? AND ts LIKE ? LIMIT 1",
        (f'%"ritual": "{name}"%', day.isoformat() + "%"),
    ).fetchone()
    return row is not None


# ------------------------------------------------------------------- context

def committed_today(repo):
    """The newest commit made today in that repo, '' if none, None if the
    check itself failed."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "log", "--since", "midnight", "-1",
             "--format=%h %s"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def fetch_headlines(feeds, per_feed=3):
    """Story titles from each feed, RSS or Atom, joined for the prompt."""
    atom = "{http://www.w3.org/2005/Atom}"
    titles = []
    for url in feeds:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "cat-server rituals"})
            with urllib.request.urlopen(req, timeout=15) as r:
                root = ET.fromstring(r.read())
            items = list(root.iter("item")) or list(root.iter(atom + "entry"))
            got = [(i.findtext("title") or i.findtext(atom + "title") or "").strip()
                   for i in items]
            titles += [t for t in got if t][:per_feed]
        except Exception as e:
            print(f"  feed failed, skipping it: {url} ({e})")
    return "; ".join(titles)


def build_context(name, cfg, db):
    """The placeholder values one ritual's prompt template gets."""
    today = date.today()
    if name == "morning_plan":
        outs = texts_on(db, "outcome", today - timedelta(days=1))
        return {"date": today.strftime("%A, %B %d"),
                "yesterday_outcomes": "; ".join(outs) or "none"}
    if name == "afternoon_review":
        plans = texts_on(db, "plan", today)
        old = texts_on(db, "plan", today - timedelta(days=7))
        return {"today_plan": "; ".join(plans) or "none",
                "week_ago_plan": "; ".join(old) or "none"}
    if name == "weight":
        row = last_of(db, "weight")
        last = f"{row[1]} on {row[0][:10]}" if row else "none"
        return {"last_weight": last}
    if name == "news":
        return {"headlines": fetch_headlines(cfg.get("feeds") or [])}
    return {}


def fill(template, ctx):
    for k, v in ctx.items():
        template = template.replace("{" + k + "}", v)
    return template


# --------------------------------------------------------------------- model

def ask_model(prompt, model, key):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = json.loads(r.read().decode("utf-8"))
    return doc["choices"][0]["message"]["content"].strip()


def build_line(name, ritual, cfg, db, key):
    """The sentence this ritual should speak right now, or None to stay quiet.

    Never raises. A failed feed, a failed git call or a failed model call all
    degrade to the plain fallback line, because a ritual that crashes is worse
    than one that speaks plainly."""
    template = ritual.get("prompt", "")
    fallback = FALLBACK.get(name, "")

    if name == "post_check":
        commit = committed_today(cfg.get("post_repo") or "")
        if commit is None:
            print(f"  {name}: could not check the repo, staying quiet")
            return None
        if commit:
            if ritual.get("on_done", "skip") != "congratulate":
                return None
            template = ritual.get("done_prompt", "")
            fallback = FALLBACK["post_check_done"]

    try:
        ctx = build_context(name, cfg, db)
    except Exception as e:
        print(f"  {name}: context failed ({e}), using the fallback line")
        return fallback or None
    if name == "news" and not ctx.get("headlines"):
        print(f"  {name}: no feed answered, using the fallback line")
        return fallback or None

    if not key:
        return fallback or None
    try:
        return ask_model(fill(template, ctx), cfg.get("model", "gpt-4o-mini"), key)
    except Exception as e:
        print(f"  {name}: model call failed ({e}), using the fallback line")
        return fallback or None


# -------------------------------------------------------------------- bridge

def say(bridge, text, dry_run=False):
    """True once the cat spoke, False when it is not reachable yet."""
    if dry_run:
        print(f"  would POST {bridge}/say: {text}")
        return True
    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        bridge + "/say", data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except urllib.error.HTTPError as e:
        if e.code == 503:
            return False  # no cat connected, the retry loop handles it
        if e.code == 409:
            return False  # cat is mid-conversation or mid-song, retry later
        print(f"  /say -> {e.code} {e.read()[:120]!r}")
        return False
    except urllib.error.URLError:
        return False  # bridge not up, same treatment


# ------------------------------------------------------------------ presence

def idle_seconds():
    """Seconds since the last keyboard or mouse input, or None when Windows
    will not say. GetTickCount wraps every 49.7 days, and dwTime comes from
    the same counter, so the subtraction is done in 32 bits on purpose."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        ticks = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((ticks - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


def presence_line(pres, cfg, key, desk_minutes):
    """The reminder sentence, model written with the fallback behind it."""
    prompt = fill(pres.get("prompt", ""), {"desk_minutes": str(desk_minutes)})
    if key and prompt:
        try:
            return ask_model(prompt, cfg.get("model", "gpt-4o-mini"), key)
        except Exception as e:
            print(f"  look_outside: model call failed ({e}), "
                  "using the fallback line")
    return FALLBACK["look_outside"]


def presence_tick(cfg, db, key, ps):
    """One pass of the desk reminder.

    Input inside the last away_minutes counts as being at the desk. Every
    remind_minutes at the desk the cat asks for a look out the window, and it
    keeps asking on that clock until a looked_outside row shows up in the
    ledger, written by the tool the cat calls when he says he looked. A full
    away_minutes with no input ends the stretch, and the next input starts a
    fresh clock."""
    pres = cfg.get("presence") or {}
    if not isinstance(pres, dict) or not pres.get("enabled", True):
        if ps.get("state") != "off":
            ps.clear()
            ps["state"] = "off"
        return
    idle = idle_seconds()
    if idle is None:
        ps["state"] = "off"
        return

    now = datetime.now()
    remind = timedelta(minutes=pres.get("remind_minutes", 20))
    away = timedelta(minutes=pres.get("away_minutes", 60))

    if timedelta(seconds=idle) >= away:
        if ps.get("state") == "desk":
            print(f"{now:%H:%M:%S}  look_outside: no input for "
                  f"{pres.get('away_minutes', 60)} minutes, going quiet")
        ps.clear()
        ps["state"] = "away"
        return

    if ps.get("state") != "desk":
        ps.clear()
        ps.update({"state": "desk", "since": now, "anchor": now, "text": None})
        print(f"{now:%H:%M:%S}  look_outside: at the desk, first reminder "
              f"around {now + remind:%H:%M}")

    row = last_of(db, "looked_outside")
    if row:
        # companion_mcp writes its timestamps with a space, this file with a
        # T. fromisoformat on 3.11+ reads both.
        try:
            ack = datetime.fromisoformat(row[0])
        except ValueError:
            ack = None
        if ack and ack > ps["anchor"]:
            ps["anchor"] = ack
            ps["text"] = None
            print(f"{now:%H:%M:%S}  look_outside: he looked, next around "
                  f"{ack + remind:%H:%M}")

    if ps["text"] is None and now >= ps["anchor"] + remind:
        ps["text"] = presence_line(
            pres, cfg, key, int((now - ps["since"]).total_seconds() // 60))

    if ps["text"] is not None:
        # No retry window like the rituals have. A cat that is unreachable or
        # mid-conversation just gets tried again on the next tick, and an
        # acknowledgment or an away hour cancels the attempt.
        if say(cfg.get("bridge", "http://127.0.0.1:8004"), ps["text"]):
            log_row(db, "reminder", ps["text"], {"reminder": "look_outside"})
            print(f"{now:%H:%M:%S}  look_outside: spoke: {ps['text']}")
            ps["anchor"] = datetime.now()
            ps["text"] = None


# ---------------------------------------------------------------------- loop

def parse_hhmm(s, day):
    try:
        h, m = str(s).split(":")
        return datetime.combine(day, dtime(int(h), int(m)))
    except Exception:
        return None


def tick(cfg, db, key, pending, done):
    """One pass: open windows for rituals whose time has come, and work every
    pending ritual that is due an attempt."""
    now = datetime.now()
    today = now.date()
    bridge = cfg.get("bridge", "http://127.0.0.1:8004")
    retry = timedelta(minutes=cfg.get("retry_minutes", 5))
    give_up = timedelta(minutes=cfg.get("give_up_minutes", 45))

    done.intersection_update({d for d in done if d[0] == today.isoformat()})

    for name, ritual in (cfg.get("rituals") or {}).items():
        if not isinstance(ritual, dict) or not ritual.get("enabled", True):
            continue
        mark = (today.isoformat(), name)
        if mark in done or name in pending:
            continue
        at = parse_hhmm(ritual.get("time"), today)
        if at is None or not (at <= now < at + give_up):
            continue
        if already_ran(db, name, today):
            done.add(mark)
            continue
        pending[name] = {"deadline": at + give_up, "next": now, "text": None}
        print(f"{now:%H:%M:%S}  {name}: time")

    for name in list(pending):
        p = pending[name]
        now = datetime.now()
        if now < p["next"]:
            continue
        mark = (now.date().isoformat(), name)
        if p["text"] is None:
            p["text"] = build_line(name, cfg["rituals"][name], cfg, db, key)
            if p["text"] is None:
                del pending[name]
                done.add(mark)
                print(f"{now:%H:%M:%S}  {name}: nothing to say")
                continue
        if say(bridge, p["text"]):
            log_row(db, "prompt", p["text"], {"ritual": name})
            del pending[name]
            done.add(mark)
            print(f"{now:%H:%M:%S}  {name}: spoke: {p['text']}")
        elif now >= p["deadline"]:
            log_row(db, "missed", p["text"],
                    {"ritual": name, "reason": "no cat connected"})
            del pending[name]
            done.add(mark)
            print(f"{now:%H:%M:%S}  {name}: missed, no cat for "
                  f"{cfg.get('give_up_minutes', 45)} minutes")
        else:
            p["next"] = now + retry
            print(f"{now:%H:%M:%S}  {name}: no cat connected, "
                  f"retrying at {p['next']:%H:%M}")


def dry_run(cfg, db, key, names):
    bridge = cfg.get("bridge", "http://127.0.0.1:8004")
    rituals = cfg.get("rituals") or {}
    pres = cfg.get("presence") if isinstance(cfg.get("presence"), dict) else {}
    known = list(rituals) + ["look_outside"]
    unknown = [n for n in names if n not in known]
    if unknown:
        sys.exit(f"no ritual called {', '.join(unknown)}. "
                 f"This file has: {', '.join(known)}")
    for name, ritual in rituals.items():
        if names and name not in names:
            continue
        if not names and not ritual.get("enabled", True):
            print(f"{name} ({ritual.get('time')}): disabled")
            continue
        text = build_line(name, ritual, cfg, db, key)
        if text is None:
            print(f"{name} ({ritual.get('time')}): would stay quiet")
        else:
            print(f"{name} ({ritual.get('time')}):")
            say(bridge, text, dry_run=True)
    if names and "look_outside" not in names:
        return
    if not pres.get("enabled", True):
        print("look_outside: disabled")
        return
    idle = idle_seconds()
    seen = ("no input clock here" if idle is None
            else f"last input {int(idle)}s ago")
    print(f"look_outside (every {pres.get('remind_minutes', 20)} min "
          f"at the desk, {seen}):")
    say(bridge, presence_line(pres, cfg, key, 20), dry_run=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("names", nargs="*",
                   help="with --dry-run, only these rituals")
    p.add_argument("--dry-run", action="store_true",
                   help="build every line now, print it, post nothing")
    p.add_argument("--db", default=DB_PATH,
                   help="another database, for testing")
    p.add_argument("--config", default=CONFIG_PATH)
    args = p.parse_args()

    cfg = load_config(args.config)
    db = open_db(args.db)
    key = read_env().get("OPENAI_API_KEY", "")
    if not key:
        print("no OPENAI_API_KEY in .env, every ritual will use its fallback line")

    if args.dry_run:
        dry_run(cfg, db, key, args.names)
        return

    enabled = [n for n, r in (cfg.get("rituals") or {}).items()
               if isinstance(r, dict) and r.get("enabled", True)]
    print(f"rituals daemon, config {args.config}")
    print(f"enabled: {', '.join(enabled) or 'nothing'}")
    pres = cfg.get("presence") if isinstance(cfg.get("presence"), dict) else {}
    if pres.get("enabled", True) and idle_seconds() is not None:
        print(f"desk reminder: every {pres.get('remind_minutes', 20)} minutes "
              f"at the desk, quiet after {pres.get('away_minutes', 60)} "
              "minutes without input")
    else:
        print("desk reminder: off")

    pending, done, presence = {}, set(), {}
    stamp = config_stamp(args.config)
    while True:
        try:
            # Pick up edits to rituals.yaml without a restart, so changing a
            # time in an editor or the dashboard just works. Open retry
            # windows are left alone; the new config applies from the next
            # ritual on.
            fresh = config_stamp(args.config)
            if fresh != stamp:
                stamp = fresh
                cfg = load_config(args.config)
                print(f"{time.strftime('%H:%M:%S')}  rituals.yaml changed, reloaded")
            tick(cfg, db, key, pending, done)
            presence_tick(cfg, db, key, presence)
            heartbeat(cfg, presence)
        except Exception as e:
            # One bad tick must never take the day's remaining rituals with it.
            print(f"{time.strftime('%H:%M:%S')}  tick failed: {e}")
        time.sleep(POLL_SECONDS)


def heartbeat(cfg, presence=None):
    try:
        enabled = [n for n, r in (cfg.get("rituals") or {}).items()
                   if isinstance(r, dict) and r.get("enabled", True)]
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.now().isoformat(timespec="seconds"),
                       "poll_seconds": POLL_SECONDS,
                       "enabled": enabled,
                       "presence": (presence or {}).get("state", "off")}, f)
    except OSError:
        pass


def config_stamp(path):
    try:
        s = os.stat(path)
        return (s.st_mtime_ns, s.st_size)
    except OSError:
        return None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
