#!/usr/bin/env python3
"""A cat that is not there.

Connects to the server the same way the real device does, so a profile can be
tested without the hardware powered on, without a microphone, and without
waiting for a wake word. It speaks by sending the text the cat's speech
recognition would have produced, and it prints everything the server sends back,
including which face the server asked for.

    python3 tools/fake_cat.py                       interactive, type to talk
    python3 tools/fake_cat.py "what time is it"     say one thing and exit
    python3 tools/fake_cat.py --listen              connect and just watch

Audio comes back as Opus frames, which this does not decode. It reports their
size instead, which is enough to prove speech synthesis ran.
"""

import argparse
import asyncio
import json
import sys
import uuid

try:
    import websockets
except ImportError:
    sys.exit("pip install websockets")

DEFAULT_URL = "ws://127.0.0.1:8000/xiaozhi/v1/"
DEVICE_ID = "aa:bb:cc:dd:ee:ff"

# The three tools the real cat announces over MCP. Declared here so a profile
# that talks about volume or brightness behaves the same against the fake one.
DEVICE_TOOLS = [
    {
        "name": "self.audio_speaker.set_volume",
        "description": "Set the volume of the audio speaker. 0 to 100.",
        "inputSchema": {
            "type": "object",
            "properties": {"volume": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["volume"],
        },
    },
    {
        "name": "self.screen.set_brightness",
        "description": "Set the brightness of the screen. 0 to 100.",
        "inputSchema": {
            "type": "object",
            "properties": {"brightness": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["brightness"],
        },
    },
    {
        "name": "self.screen.set_theme",
        "description": "Set the theme of the screen, light or dark.",
        "inputSchema": {
            "type": "object",
            "properties": {"theme": {"type": "string", "enum": ["light", "dark"]}},
            "required": ["theme"],
        },
    },
]

C = {"face": "\033[95m", "say": "\033[92m", "dim": "\033[90m",
     "warn": "\033[93m", "off": "\033[0m"}


def out(colour, label, text):
    print(f"{C[colour]}{label:<8}{C['off']} {text}", flush=True)


class FakeCat:
    def __init__(self, url, device_id):
        self.url = url
        self.device_id = device_id
        self.ws = None
        self.session_id = None
        self.audio_frames = 0
        self.audio_bytes = 0

    async def connect(self):
        headers = {
            "device-id": self.device_id,
            "client-id": str(uuid.uuid4()),
            "protocol-version": "1",
        }
        self.ws = await websockets.connect(
            self.url, additional_headers=headers, max_size=None
        )
        await self.send({
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "features": {"mcp": True},
            "audio_params": {
                "format": "opus", "sample_rate": 16000,
                "channels": 1, "frame_duration": 60,
            },
        })
        out("dim", "conn", f"{self.url} as {self.device_id}")

    async def send(self, obj):
        await self.ws.send(json.dumps(obj, ensure_ascii=False))

    async def say(self, text):
        """Send what speech recognition would have produced."""
        out("dim", "you", text)
        await self.send({"type": "listen", "mode": "manual", "state": "detect",
                         "text": text, "source": "text"})

    async def pump(self):
        async for raw in self.ws:
            if isinstance(raw, bytes):
                self.audio_frames += 1
                self.audio_bytes += len(raw)
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                out("warn", "raw", raw[:200])
                continue
            await self.on_message(msg)

    async def on_message(self, msg):
        kind = msg.get("type")
        if kind == "hello":
            self.session_id = msg.get("session_id")
            out("dim", "hello", f"session {self.session_id}")
            # Announce the body controls the way the firmware does.
            await self.send({
                "type": "mcp",
                "payload": {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2024-11-05",
                                       "capabilities": {"tools": {}},
                                       "clientInfo": {"name": "fake-cat",
                                                      "version": "1.0"}}},
            })
        elif kind == "llm":
            out("face", "face", f"{msg.get('text','')}  {msg.get('emotion','')}")
        elif kind == "tts":
            state = msg.get("state")
            if state == "sentence_start":
                out("say", "says", msg.get("text", ""))
            elif state == "stop":
                if self.audio_frames:
                    out("dim", "audio",
                        f"{self.audio_frames} opus frames, {self.audio_bytes} bytes")
                self.audio_frames = self.audio_bytes = 0
        elif kind == "mcp":
            payload = msg.get("payload", {})
            method = payload.get("method")
            if method == "tools/list":
                await self.send({
                    "type": "mcp",
                    "payload": {"jsonrpc": "2.0", "id": payload.get("id"),
                                "result": {"tools": DEVICE_TOOLS}},
                })
                out("dim", "mcp", "sent the three body tools")
            elif method == "tools/call":
                name = payload.get("params", {}).get("name")
                args = payload.get("params", {}).get("arguments")
                out("face", "body", f"{name} {args}")
                await self.send({
                    "type": "mcp",
                    "payload": {"jsonrpc": "2.0", "id": payload.get("id"),
                                "result": {"content": [{"type": "text", "text": "ok"}],
                                           "isError": False}},
                })
            elif payload.get("result") is not None and payload.get("id") == 1:
                await self.send({
                    "type": "mcp",
                    "payload": {"jsonrpc": "2.0", "method": "notifications/initialized"},
                })
        elif kind in ("goodbye",):
            out("warn", kind, json.dumps(msg, ensure_ascii=False)[:200])
        else:
            out("dim", kind or "?", json.dumps(msg, ensure_ascii=False)[:200])


async def run(args):
    cat = FakeCat(args.url, args.device_id)
    await cat.connect()
    pump = asyncio.create_task(cat.pump())

    if args.text:
        await asyncio.sleep(1.0)
        await cat.say(" ".join(args.text))
        await asyncio.sleep(args.wait)
    elif args.listen:
        await pump
    else:
        loop = asyncio.get_running_loop()
        print("type something and press enter, or ctrl-c to stop")
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if line:
                await cat.say(line)
    pump.cancel()
    await cat.ws.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("text", nargs="*", help="say this and exit")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--device-id", default=DEVICE_ID)
    p.add_argument("--listen", action="store_true", help="connect and watch only")
    p.add_argument("--wait", type=float, default=25.0,
                   help="seconds to wait for the reply in one-shot mode")
    args = p.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
