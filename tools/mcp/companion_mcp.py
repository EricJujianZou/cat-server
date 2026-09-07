#!/usr/bin/env python3
"""The cat's ledger: plans, outcomes, weight, ideas, notes and focus blocks.

Runs inside the container, launched by the server as a stdio MCP server. It
writes everything to one sqlite table in data/companion.db, which the daemon
that speaks the scheduled prompts shares. Every event is one row with the
details in a JSON column. Focus blocks are the exception: closing one updates
the row that opened it, so a block is always exactly one row.

The shopping list lives in the same file as its own table, because its rows
change state and get deleted, which the append-only log is the wrong shape
for. The dashboard's shopping page reads and writes the same table.

The model calls these tools while the owner talks. The answers come back as
short sentences it can speak, and get_context hands it enough of the recent
record to compare a day against its plan without reading the whole table.

For testing outside the container, COMPANION_DB points the whole file at a
scratch database. Inside the container the default path is the mounted one.

    COMPANION_DB=C:\\somewhere\\scratch.db py -3.13 tools\\mcp\\companion_mcp.py
"""

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

DB = os.environ.get("COMPANION_DB",
                    "/opt/xiaozhi-esp32-server/data/companion.db")

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts TEXT NOT NULL, "
    "kind TEXT NOT NULL, "
    "text TEXT NOT NULL DEFAULT '', "
    "data TEXT NOT NULL DEFAULT '{}')"
)

SHOPPING_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS shopping ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "text TEXT NOT NULL, "
    "added_at TEXT NOT NULL, "
    "bought INTEGER NOT NULL DEFAULT 0)"
)

mcp = FastMCP("companion")


def db():
    """A fresh connection per call. Another process writes to the same file,
    so connections stay short. Not WAL: the file is shared across the
    container, WSL and Windows through the drive mount, and WAL's shared
    memory does not work across that boundary."""
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(SCHEMA)
    conn.execute(SHOPPING_SCHEMA)
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def put(kind, text="", data=None):
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO log (ts, kind, text, data) VALUES (?, ?, ?, ?)",
            (now(), kind, text, json.dumps(data or {}, ensure_ascii=False)))


def parse(blob):
    try:
        doc = json.loads(blob)
        return doc if isinstance(doc, dict) else {}
    except ValueError:
        return {}


def day_of(ts):
    return ts[:10]


def spoken_date(day):
    """2026-08-17 as `August 17`, which survives being read out loud."""
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return day
    return d.strftime("%B ") + str(d.day)


def clip(text, n=90):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


# Small on purpose. It only has to stop "the", "a" and their relatives from
# making every idea look like every other idea.
STOPWORDS = frozenset("""
a about an and are as at be but by could do for from had has have i if in into
is it its just like me my of on or our so some that the their then there this
to was we what when which will with would you your
""".split())


CJK = re.compile(r"[\u4e00-\u9fff]")


def words(text):
    """English split by word with stopwords out. Chinese split into character
    pairs, because the profile is spoken to in Chinese and spoken Chinese has
    no spaces to split on."""
    out = set()
    for run in re.findall(r"[a-z0-9']+|[\u4e00-\u9fff]+", text.lower()):
        if CJK.match(run):
            if len(run) == 1:
                out.add(run)
            else:
                out.update(run[i:i + 2] for i in range(len(run) - 1))
        elif run not in STOPWORDS and len(run) > 1:
            out.add(run)
    return out


# --------------------------------------------------------------------- tools

@mcp.tool()
def log_plan(text: str) -> str:
    """Record what the user plans to get done today.

    Call this whenever the user states a plan for the day, whether the cat
    asked for it or they volunteered it. Store the plan in their own words.
    """
    put("plan", text.strip())
    return "Plan logged for today."


@mcp.tool()
def log_outcome(text: str, completion: float) -> str:
    """Record what actually got done, against this morning's plan.

    Call this when the user reports on their day. completion is your own
    estimate, from 0 to 1, of how much of the stated plan happened, judged
    from what they said. Be honest rather than kind. Fetch get_context first
    so you can compare against the actual plan.
    """
    try:
        c = max(0.0, min(1.0, float(completion)))
    except (TypeError, ValueError):
        return "completion has to be a number from 0 to 1."
    put("outcome", text.strip(), {"completion": round(c, 2)})
    return f"Outcome logged at {c:.0%} of the plan."


@mcp.tool()
def log_weight(value: float, unit: str = "kg") -> str:
    """Record the user's weight. unit is kg, lb or jin.

    Call this when the user tells you their weight. Confirm it back in a few
    words and do not comment on the number itself.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "The weight has to be a number."
    u = (unit or "kg").strip().lower()
    factor = {"kg": 1.0, "kgs": 1.0, "kilogram": 1.0, "kilograms": 1.0,
              "lb": 0.45359237, "lbs": 0.45359237,
              "pound": 0.45359237, "pounds": 0.45359237,
              "jin": 0.5, "斤": 0.5}.get(u)
    if factor is None:
        return f"I do not know the unit {unit!r}. Use kg, lb or jin."
    kg = round(v * factor, 2)
    put("weight", f"{v:g} {u}", {"kg": kg, "value": v, "unit": u})
    return f"Logged {kg:g} kilograms."


@mcp.tool()
def log_idea(text: str) -> str:
    """Record an idea the user spoke out loud, and get back the closest past
    ideas so you can say what it reminds you of.

    Call this whenever the user shares an idea. The answer lists up to five
    earlier ideas ranked by how many words they share with this one, each with
    its date. If one is close, mention it and its date in a sentence.
    """
    text = text.strip()
    new_words = words(text)
    with closing(db()) as conn, conn:
        rows = conn.execute(
            "SELECT ts, text FROM log WHERE kind='idea' ORDER BY id DESC"
        ).fetchall()
        conn.execute(
            "INSERT INTO log (ts, kind, text, data) VALUES (?, 'idea', ?, '{}')",
            (now(), text))
    scored = []
    for ts, old in rows:
        overlap = len(new_words & words(old))
        if overlap:
            scored.append((overlap, ts, old))
    scored.sort(key=lambda x: (-x[0], x[1]))
    if not scored:
        return "Idea logged. Nothing similar in the ledger yet."
    lines = [f"on {spoken_date(day_of(ts))}: {clip(old)}"
             for _, ts, old in scored[:5]]
    return "Idea logged. Closest past ideas: " + "; ".join(lines)


@mcp.tool()
def log_note(text: str) -> str:
    """Record the user's end of day note.

    Call this when the user winds the day down with a thought they want kept,
    anything that is not a plan, an outcome or an idea.
    """
    put("note", text.strip())
    return "Note logged."


@mcp.tool()
def focus_start(minutes: int, intent: str) -> str:
    """Start a focus block.

    Call this when the user announces a stretch of focused work, usually
    around fifty minutes, and what it is for. Confirm in a few words and let
    them get to it.
    """
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "minutes has to be a number."
    put("focus", intent.strip(), {"minutes": m, "open": True})
    return f"Focus block started, {m} minutes for {clip(intent, 60)}."


@mcp.tool()
def focus_end(outcome: str, completed: bool) -> str:
    """Close the most recent open focus block with what came of it.

    Call this when the user reports back after a focus block. completed is
    whether they finished what the block was for, judged from what they said.
    """
    with closing(db()) as conn, conn:
        rows = conn.execute(
            "SELECT id, ts, text, data FROM log WHERE kind='focus' "
            "ORDER BY id DESC").fetchall()
        for rid, ts, intent, blob in rows:
            data = parse(blob)
            if not data.get("open"):
                continue
            data.update({"open": False, "outcome": outcome.strip(),
                         "completed": bool(completed), "ended": now()})
            conn.execute("UPDATE log SET data=? WHERE id=?",
                         (json.dumps(data, ensure_ascii=False), rid))
            done = "finished" if completed else "not finished"
            return (f"Focus block closed, {done}. "
                    f"It was for {clip(intent, 60)}.")
    return "There is no open focus block to close."


@mcp.tool()
def looked_outside() -> str:
    """Record that the user looked out the window and rested their eyes.

    Call this when the user says they looked outside, looked out the window,
    or gave their eyes a break, whether or not a reminder asked them to. It
    resets the desk reminder clock, so the next reminder comes twenty minutes
    from now. Acknowledge in a few words and let them get back to it.
    """
    put("looked_outside")
    return "Noted, the reminder clock starts over."


def find_item(rows, item):
    """The row whose text best matches what the user said. Exact beats
    substring in either direction, all case-insensitive, because "the milk"
    and "牛奶" have to land on the row that was added as "milk" or "牛奶"."""
    want = " ".join(str(item).split()).lower()
    if not want:
        return None
    for rid, text in rows:
        if text.lower() == want:
            return rid, text
    for rid, text in rows:
        if want in text.lower() or text.lower() in want:
            return rid, text
    return None


@mcp.tool()
def shopping_add(items: list[str]) -> str:
    """Add items to the shopping list.

    Call this whenever the user mentions something they need to buy or asks
    to put something on the list. Pass every item they named in the one call,
    each as its own short entry, in their words.
    """
    cleaned = []
    for item in items or []:
        item = " ".join(str(item).split())
        if item:
            cleaned.append(item)
    if not cleaned:
        return "Nothing was named, so the list is unchanged."
    added, already = [], []
    with closing(db()) as conn, conn:
        have = {t.lower() for (t,) in conn.execute(
            "SELECT text FROM shopping WHERE bought=0")}
        for item in cleaned:
            if item.lower() in have:
                already.append(item)
                continue
            conn.execute(
                "INSERT INTO shopping (text, added_at) VALUES (?, ?)",
                (item, now()))
            have.add(item.lower())
            added.append(item)
    parts = []
    if added:
        parts.append("Added to the shopping list: " + ", ".join(added) + ".")
    if already:
        parts.append("Already on it: " + ", ".join(already) + ".")
    return " ".join(parts)


@mcp.tool()
def shopping_read() -> str:
    """Read the current shopping list, the items not yet bought.

    Call this when the user asks what is on the list, or after they say yes
    to hearing it before heading out. Speak the items back in the language
    the user is speaking right now.
    """
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT text FROM shopping WHERE bought=0 ORDER BY id").fetchall()
    if not rows:
        return "The shopping list is empty."
    items = [t for (t,) in rows]
    word = "item" if len(items) == 1 else "items"
    # The trailing sentence is for the model, which otherwise falls back to
    # the profile's default language for post-tool replies. It paraphrases
    # rather than quotes, so the instruction does not reach the speaker.
    return (f"{len(items)} {word} to buy: " + ", ".join(items) + ". "
            "Read these out in the language the user spoke last, keeping "
            "each item's own wording where the voice can say it.")


@mcp.tool()
def shopping_bought(item: str, remove: bool = False) -> str:
    """Mark one shopping list item as bought, or take it off the list.

    Call this with remove false when the user says they bought something.
    Call it with remove true when they say an item should not be on the list
    at all. The match is loose, so their wording need not be exact.
    """
    with closing(db()) as conn, conn:
        rows = conn.execute(
            "SELECT id, text FROM shopping WHERE bought=0 ORDER BY id"
        ).fetchall()
        hit = find_item(rows, item)
        if not hit:
            if not rows:
                return "The shopping list is already empty."
            # The list may hold the same thing under another language's name,
            # which only the model can see. Hand it the list and the retry.
            return (f"No item called {str(item).strip()} was found. The list "
                    "holds: " + ", ".join(t for _, t in rows) + ". If one of "
                    "those is the same thing in other words, call "
                    "shopping_bought again with it exactly as written here. "
                    "Do not tell the user it is marked until that succeeds.")
        rid, text = hit
        if remove:
            conn.execute("DELETE FROM shopping WHERE id=?", (rid,))
            return f"Took {text} off the list."
        conn.execute("UPDATE shopping SET bought=1 WHERE id=?", (rid,))
        left = len(rows) - 1
    if left:
        return f"Marked {text} bought. {left} still to buy."
    return f"Marked {text} bought. That was the last one."


@mcp.tool()
def shopping_clear_bought() -> str:
    """Clear the bought items off the shopping list.

    Call this when the user says the shopping is done or asks to tidy the
    list. Items not yet bought stay where they are.
    """
    with closing(db()) as conn, conn:
        n = conn.execute("DELETE FROM shopping WHERE bought=1").rowcount
        left = conn.execute(
            "SELECT COUNT(*) FROM shopping WHERE bought=0").fetchone()[0]
    if not n:
        return "There were no bought items to clear."
    word = "item" if n == 1 else "items"
    tail = f" {left} still to buy." if left else " The list is now empty."
    return f"Cleared {n} bought {word}.{tail}"


@mcp.tool()
def get_context(days: int = 7) -> str:
    """The recent record: each day's plan and outcome, the 30 day completion
    rate, the weight trend, and any open focus block.

    Call this before logging an outcome, when the user asks how they are
    doing, or when you are about to push back on a plan. Compare what it says
    against what the user is telling you, and quote the numbers as they are.
    """
    try:
        n = max(1, min(31, int(days)))
    except (TypeError, ValueError):
        n = 7
    today = datetime.now().date()
    since_day = (today - timedelta(days=n - 1)).isoformat()
    since_30 = (today - timedelta(days=29)).isoformat()
    since_14 = (today - timedelta(days=13)).isoformat()

    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT ts, kind, text, data FROM log WHERE ts >= ? ORDER BY id",
            (since_30,)).fetchall()

    by_day = {}
    completions = []
    weights = []
    open_focus = None
    for ts, kind, text, blob in rows:
        day = day_of(ts)
        data = parse(blob)
        if kind == "outcome" and isinstance(data.get("completion"), (int, float)):
            completions.append(float(data["completion"]))
        if kind == "weight" and isinstance(data.get("kg"), (int, float)):
            if day >= since_14:
                weights.append((day, float(data["kg"])))
        if kind == "focus" and data.get("open"):
            open_focus = (ts, text, data)
        if day < since_day:
            continue
        pieces = by_day.setdefault(day, [])
        if kind == "plan":
            pieces.append("plan: " + clip(text))
        elif kind == "outcome":
            c = data.get("completion")
            done = f"done at {float(c):.0%}: " if isinstance(c, (int, float)) else "done: "
            pieces.append(done + clip(text))
        elif kind == "note":
            pieces.append("note: " + clip(text, 60))
        elif kind == "missed":
            pieces.append("missed: " + clip(text, 60))
        elif kind == "prompt":
            pieces.append("prompted: " + clip(text, 60))
        elif kind == "focus":
            state = ("open" if data.get("open")
                     else "finished" if data.get("completed") else "not finished")
            pieces.append(f"focus {data.get('minutes', '?')} min ({state}): "
                          + clip(text, 50))

    lines = [f"Last {n} days:"]
    for i in range(n):
        day = (today - timedelta(days=n - 1 - i)).isoformat()
        pieces = by_day.get(day)
        if pieces:
            lines.append(spoken_date(day) + ": " + " | ".join(pieces))
    if len(lines) == 1:
        lines.append("nothing logged.")

    if completions:
        avg = sum(completions) / len(completions)
        word = "outcome" if len(completions) == 1 else "outcomes"
        lines.append(f"30 day completion: {avg:.0%} across "
                     f"{len(completions)} logged {word}.")
    else:
        lines.append("30 day completion: no outcomes logged yet.")

    if len(weights) >= 2:
        (d1, w1), (d2, w2) = weights[0], weights[-1]
        diff = w2 - w1
        word = "up" if diff > 0 else "down" if diff < 0 else "flat"
        lines.append(f"Weight over 14 days: {w1:g} kg on {spoken_date(d1)}, "
                     f"{w2:g} kg on {spoken_date(d2)}, "
                     f"{word} {abs(diff):.1f} kg.")
    elif len(weights) == 1:
        lines.append(f"Weight: one reading, {weights[0][1]:g} kg on "
                     f"{spoken_date(weights[0][0])}.")

    if open_focus:
        ts, intent, data = open_focus
        lines.append(f"Open focus block: {data.get('minutes', '?')} minutes "
                     f"for {clip(intent, 60)}, started {ts[11:16]}.")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
