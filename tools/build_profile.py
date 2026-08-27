#!/usr/bin/env python3
"""Builds the running config from config/base.yaml plus one profile.

Everything the cat is comes from three files in config/profiles/<name>/:

    profile.yaml   voice, model, and any override of base.yaml
    prompt.md      the system prompt, verbatim
    mcp.json       the MCP servers this profile can call

This script merges them over config/base.yaml, substitutes ${VAR} from .env,
and writes the two files the server actually reads:

    data/.config.yaml
    data/.mcp_server_settings.json

Nothing else in the repo needs editing to change what the cat does.

Usage:
    python3 tools/build_profile.py list
    python3 tools/build_profile.py use <name>
    python3 tools/build_profile.py show
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
PROFILES = os.path.join(CONFIG, "profiles")
DATA = os.path.join(ROOT, "data")
ACTIVE = os.path.join(DATA, ".active-profile")
STAMP = os.path.join(DATA, ".build-stamp")

try:
    import yaml
except ImportError:
    sys.exit(
        "pyyaml is missing. This script is meant to run inside WSL, where it is\n"
        "already installed. From PowerShell use .\\cat.ps1 instead, which shells\n"
        "into WSL for you."
    )


def source_hash(name):
    """A fingerprint of everything that goes into a build.

    Only files under config/ are read, so this never touches .env or the built
    config, and the hash is the same on any machine with the same source. It is
    what lets the dashboard say "you edited something and have not rebuilt"
    without comparing timestamps, which lie: rebuilding an unchanged profile
    moves the mtime without changing the outcome.
    """
    h = hashlib.sha256()
    paths = [os.path.join(CONFIG, "base.yaml")]
    pdir = os.path.join(PROFILES, name)
    if os.path.isdir(pdir):
        paths += [os.path.join(pdir, f) for f in sorted(os.listdir(pdir))]
    for path in paths:
        if not os.path.isfile(path):
            continue
        h.update(os.path.basename(path).encode("utf-8"))
        h.update(open(path, "rb").read())
    return h.hexdigest()[:16]


def read_stamp():
    try:
        return json.load(open(STAMP, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_env():
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        sys.exit("no .env here. copy .env.example to .env and fill it in.")
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def substitute(text, env):
    missing = sorted({k for k in re.findall(r"\$\{(\w+)\}", text) if not env.get(k)})
    if missing:
        sys.exit("These are still blank in .env: " + ", ".join(missing))
    return re.sub(r"\$\{(\w+)\}", lambda m: env[m.group(1)], text)


def deep_merge(base, over):
    """Dict values merge key by key. Everything else replaces outright, so a
    profile that sets a list gets exactly that list rather than an append."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def list_profiles():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(
        d
        for d in os.listdir(PROFILES)
        if os.path.isfile(os.path.join(PROFILES, d, "profile.yaml"))
    )


def describe(name):
    path = os.path.join(PROFILES, name, "profile.yaml")
    try:
        doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
        return doc.get("description", "")
    except Exception:
        return ""


def cmd_list():
    active = current_profile()
    names = list_profiles()
    if not names:
        print("no profiles in config/profiles/")
        return
    width = max(len(n) for n in names)
    for n in names:
        mark = "*" if n == active else " "
        print(f" {mark} {n.ljust(width)}  {describe(n)}")
    print()
    print("* is the profile currently built into data/. Switch with:")
    print("    python3 tools/build_profile.py use <name>")


def current_profile():
    if os.path.exists(ACTIVE):
        return open(ACTIVE, encoding="utf-8").read().strip()
    return None


def cmd_show():
    name = current_profile()
    if not name:
        print("no profile built yet")
        return
    print(f"active profile: {name}")
    print(f"  {describe(name)}")
    mcp = os.path.join(DATA, ".mcp_server_settings.json")
    if os.path.exists(mcp):
        doc = json.load(open(mcp, encoding="utf-8"))
        servers = sorted(doc.get("mcpServers", {}))
        print("  mcp servers: " + (", ".join(servers) if servers else "none"))


def cmd_use(name):
    pdir = os.path.join(PROFILES, name)
    if not os.path.isfile(os.path.join(pdir, "profile.yaml")):
        sys.exit(
            f"no profile called {name!r}. Available: "
            + ", ".join(list_profiles() or ["(none)"])
        )

    env = read_env()
    os.makedirs(DATA, exist_ok=True)

    base = yaml.safe_load(substitute(open(os.path.join(CONFIG, "base.yaml"), encoding="utf-8").read(), env)) or {}
    over = yaml.safe_load(substitute(open(os.path.join(pdir, "profile.yaml"), encoding="utf-8").read(), env)) or {}

    # description is documentation for the profile list, not server config
    over.pop("description", None)
    # notes is free text for whoever edits the profile
    over.pop("notes", None)

    merged = deep_merge(base, over)

    prompt_path = os.path.join(pdir, "prompt.md")
    if os.path.exists(prompt_path):
        merged["prompt"] = open(prompt_path, encoding="utf-8").read().strip() + "\n"

    out = os.path.join(DATA, ".config.yaml")
    header = (
        f"# GENERATED. Do not edit this file, your changes will be overwritten.\n"
        f"# Built from config/base.yaml + config/profiles/{name}/\n"
        f"# Rebuild with: python3 tools/build_profile.py use {name}\n\n"
    )
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False, width=100)

    mcp_src = os.path.join(pdir, "mcp.json")
    mcp_dst = os.path.join(DATA, ".mcp_server_settings.json")
    if os.path.exists(mcp_src):
        raw = substitute(open(mcp_src, encoding="utf-8").read(), env)
        doc = json.loads(raw)
        doc.pop("des", None)
        with open(mcp_dst, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        servers = sorted(doc.get("mcpServers", {}))
    elif os.path.exists(mcp_dst):
        os.remove(mcp_dst)
        servers = []
    else:
        servers = []

    with open(ACTIVE, "w", encoding="utf-8", newline="\n") as f:
        f.write(name + "\n")

    with open(STAMP, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"profile": name, "hash": source_hash(name), "at": time.time()},
                  f, indent=2)
        f.write("\n")

    print(f"built profile {name!r}")
    print(f"  voice:  {merged.get('TTS', {}).get('EdgeTTS', {}).get('voice', '?')}")
    print(f"  model:  {merged.get('LLM', {}).get('OpenAILLM', {}).get('model_name', '?')}")
    print(f"  mcp:    {', '.join(servers) if servers else 'none'}")
    print()
    if not restart():
        # A restart that failed leaves the container on the old build, so this
        # must not exit zero. The dashboard reads the exit code to decide
        # whether to clear its "not live yet" banner, and so does any script.
        sys.exit(1)


def restart():
    """Restart the container if docker is reachable, otherwise say so.

    Returns True only when the container actually came back."""
    try:
        r = subprocess.run(
            ["docker", "compose", "restart"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("docker not reachable from here. Restart it yourself with:")
        print("    docker compose restart")
        return False
    if r.returncode == 0:
        print("cat-server restarted, the new profile is live")
        return True
    print("docker compose restart failed:")
    print(r.stderr.strip()[:500])
    return False


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "list":
        cmd_list()
    elif cmd == "show":
        cmd_show()
    elif cmd == "use":
        if len(args) < 2:
            sys.exit("which profile? Try: python3 tools/build_profile.py list")
        cmd_use(args[1])
    else:
        sys.exit(f"unknown command {cmd!r}. Try list, use or show.")


if __name__ == "__main__":
    main()
