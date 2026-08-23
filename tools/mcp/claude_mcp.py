#!/usr/bin/env python3
"""Lets the cat answer "what is Claude doing".

Runs inside the container, launched by the server as a stdio MCP server. It
holds no state and reads no files. All it does is ask the Windows side, which is
tools/claude_status_agent.py listening on 127.0.0.1:8765, and hand the answer to
the model.

Start the Windows half first, or these tools report that nothing is listening:

    py -3.13 tools\\claude_status_agent.py
"""

import json
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

AGENT = "http://127.0.0.1:8765"

mcp = FastMCP("claude-code")


def ask(path):
    try:
        with urllib.request.urlopen(AGENT + path, timeout=6) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError:
        return None


@mcp.tool()
def claude_status() -> str:
    """What the user's Claude Code sessions are doing right now.

    Use this when asked about Claude, about a build, about whether something
    finished, or whether anything needs the user. Read the answer out as one
    sentence and stop.
    """
    doc = ask("/status")
    if doc is None:
        return (
            "I cannot see the sessions right now. The status agent on the "
            "computer is not running."
        )
    return doc.get("spoken", "I am not sure what is running.")


@mcp.tool()
def claude_sessions() -> str:
    """Every open Claude Code session, with its project and what it is doing.

    Only use this when asked for a list. For a single answer use claude_status,
    because a list is hard to follow out loud.
    """
    doc = ask("/status")
    if doc is None:
        return "The status agent on the computer is not running."
    sessions = doc.get("sessions", [])
    if not sessions:
        return "Nothing is running."
    parts = []
    for s in sessions:
        where = s.get("project") or s.get("name")
        doing = s.get("doing") or s.get("status") or "open"
        parts.append(f"{where} is {doing}")
    return ", ".join(parts) + "."


if __name__ == "__main__":
    mcp.run(transport="stdio")
