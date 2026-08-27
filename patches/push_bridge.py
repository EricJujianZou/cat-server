"""Server push, so something outside the server can reach the cat.

The stock server only ever speaks in reply to the wake word. Nothing can change
the cat's face or make it say a sentence on its own. This adds a small HTTP
listener on port 8004 that does both, and a registry of live connections for it
to aim at.

This file is mounted into the container as core/push_bridge.py. It is additive.
The only edit to a stock file is two lines in core/connection.py that call
register() once a websocket is up, and patches/README.md records exactly what
those are.

    GET  /devices        which cats are connected right now
    POST /face           {"emoji": "\U0001f914"} change the face
    POST /say            {"text": "..."} speak a sentence out loud
    POST /raw            {"message": {...}} send arbitrary JSON down the socket

Port 8004 binds to 0.0.0.0 inside WSL, so Windows reaches it on 127.0.0.1:8004.
It has no authentication, which is fine while it is bound to a laptop on a home
network and is not fine on a VPS. Put it behind a token before it moves.

There is also a keepalive. The firmware marks the audio channel dead 120
seconds after the last packet it received from the server, so a socket the
server is happy to keep open still dies on the cat's side if nothing comes
down it. Every 90 seconds this re-sends each live connection the face it is
already showing, which resets that timer without changing anything visible.
Set PUSH_KEEPALIVE_SECONDS=0 in the container's environment to turn it off.
"""

import asyncio
import os
import time
import uuid

from aiohttp import web

from config.logger import setup_logging
from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.utils.textUtils import EMOJI_MAP

TAG = __name__
logger = setup_logging()

PORT = 8004

# The firmware closes the audio channel 120 seconds after the last packet it
# received from the server (protocol.cc, kTimeoutSeconds), and any
# application-level JSON frame resets that clock. Transport-level websocket
# pings do not, because the firmware's application layer never sees them. 90
# seconds sits safely inside the 120 with room for a slow send. 0 disables.
KEEPALIVE_SECONDS = int(os.environ.get("PUSH_KEEPALIVE_SECONDS", "90"))

# A pushed line must not cut off a conversation or a song. The connection
# tracks its last real activity (mic audio in, audio out, listen events, and
# nothing else, so the keepalive does not count), and /say refuses with a 409
# until the cat has been quiet this long. The rituals daemon treats that
# refusal like an absent cat and retries later. 0 disables the guard, and a
# caller that really means it can send {"force": true}.
QUIET_SECONDS = int(os.environ.get("PUSH_QUIET_SECONDS", "120"))

# The face each device is currently showing, so the keepalive can repeat it
# rather than reset every cat to neutral. device_id -> emoji.
NEUTRAL = "\U0001F636"
LAST_FACE = {}

# device_id -> ConnectionHandler. Entries are pruned when their socket closes.
CONNECTIONS = {}
_server_started = False


def register(conn):
    """Called from ConnectionHandler.handle_connection once the socket is up."""
    device_id = getattr(conn, "device_id", None) or "unknown"
    CONNECTIONS[device_id] = conn
    logger.bind(tag=TAG).info(f"push bridge: {device_id} connected")
    _ensure_server()


def _ensure_server():
    global _server_started
    if _server_started:
        return
    _server_started = True
    asyncio.create_task(_serve())
    if KEEPALIVE_SECONDS > 0:
        asyncio.create_task(_keepalive())


async def _keepalive():
    """Sends each live cat its own face again, on a timer, forever.

    This exists purely to reset the firmware's 120 second dead-channel timer.
    An "llm" frame is used because it is the message type /face already sends,
    so it is known to be harmless: the firmware redraws the face it is already
    drawing and nothing else happens. See the module docstring.
    """
    while True:
        await asyncio.sleep(KEEPALIVE_SECONDS)
        for device_id, conn in _live().items():
            emoji = LAST_FACE.get(device_id, NEUTRAL)
            try:
                await conn.websocket.send(
                    _json({"type": "llm", "text": emoji,
                           "emotion": EMOJI_MAP.get(emoji, "neutral"),
                           "session_id": conn.session_id})
                )
            except Exception as e:
                logger.bind(tag=TAG).info(
                    f"push bridge: keepalive to {device_id} failed: {e}")


def _live():
    """Connections whose websocket is still open."""
    out = {}
    for device_id, conn in list(CONNECTIONS.items()):
        ws = getattr(conn, "websocket", None)
        if ws is None:
            CONNECTIONS.pop(device_id, None)
            continue
        state = getattr(ws, "state", None)
        if state is not None and getattr(state, "name", "") == "CLOSED":
            CONNECTIONS.pop(device_id, None)
            continue
        out[device_id] = conn
    return out


def _pick(device_id=None):
    live = _live()
    if device_id:
        return live.get(device_id)
    return next(iter(live.values()), None)


async def _devices(request):
    return web.json_response({"devices": sorted(_live())})


async def _face(request):
    body = await request.json()
    emoji = body.get("emoji", "\U0001f642")
    conn = _pick(body.get("device_id"))
    if conn is None:
        return web.json_response({"error": "no cat connected"}, status=503)
    emotion = EMOJI_MAP.get(emoji)
    if emotion is None:
        return web.json_response(
            {"error": f"{emoji} is not one of the firmware faces",
             "faces": EMOJI_MAP},
            status=400,
        )
    await conn.websocket.send(
        _json({"type": "llm", "text": emoji, "emotion": emotion,
               "session_id": conn.session_id})
    )
    # Remembered so the keepalive repeats this face rather than resetting it.
    LAST_FACE[getattr(conn, "device_id", None) or "unknown"] = emoji
    return web.json_response({"ok": True, "emotion": emotion})


async def _say(request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "nothing to say"}, status=400)
    conn = _pick(body.get("device_id"))
    if conn is None:
        return web.json_response({"error": "no cat connected"}, status=503)

    if getattr(conn, "tts", None) is None:
        return web.json_response(
            {"error": "the cat connected but speech synthesis is not up yet"},
            status=503,
        )

    if QUIET_SECONDS > 0 and not body.get("force"):
        speaking = bool(getattr(conn, "client_is_speaking", False))
        last = getattr(conn, "last_activity_time", 0) or 0
        quiet_for = time.time() - last / 1000
        if speaking or quiet_for < QUIET_SECONDS:
            return web.json_response(
                {"error": "cat is busy", "busy": True, "speaking": speaking,
                 "quiet_for_seconds": max(0, int(quiet_for))},
                status=409,
            )

    # The synthesis thread drops any message whose sentence_id does not match
    # the one the connection is currently on, so claim the connection first.
    sentence_id = str(uuid.uuid4().hex)
    conn.sentence_id = sentence_id
    conn.client_abort = False
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(sentence_id=sentence_id,
                      sentence_type=SentenceType.FIRST,
                      content_type=ContentType.ACTION)
    )
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(sentence_id=sentence_id,
                      sentence_type=SentenceType.MIDDLE,
                      content_type=ContentType.TEXT,
                      content_detail=text)
    )
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(sentence_id=sentence_id,
                      sentence_type=SentenceType.LAST,
                      content_type=ContentType.ACTION)
    )
    return web.json_response({"ok": True, "spoke": text})


async def _raw(request):
    body = await request.json()
    message = body.get("message")
    if message is None:
        return web.json_response({"error": "no message"}, status=400)
    conn = _pick(body.get("device_id"))
    if conn is None:
        return web.json_response({"error": "no cat connected"}, status=503)
    await conn.websocket.send(_json(message))
    return web.json_response({"ok": True})


def _json(obj):
    import json

    return json.dumps(obj, ensure_ascii=False)


async def _serve():
    app = web.Application()
    app.add_routes(
        [
            web.get("/devices", _devices),
            web.post("/face", _face),
            web.post("/say", _say),
            web.post("/raw", _raw),
        ]
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    try:
        await site.start()
        logger.bind(tag=TAG).info(f"push bridge listening on {PORT}")
    except Exception as e:
        logger.bind(tag=TAG).error(f"push bridge failed to bind {PORT}: {e}")
