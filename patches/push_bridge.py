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
"""

import asyncio
import uuid

from aiohttp import web

from config.logger import setup_logging
from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.utils.textUtils import EMOJI_MAP

TAG = __name__
logger = setup_logging()

PORT = 8004

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
