# patches

Two files mounted over the stock image so the server can reach the cat without
waiting for the wake word. Remove the two volume lines from `docker-compose.yml`
and the container is stock again.

| File | What it is |
|---|---|
| `push_bridge.py` | New. Mounted as `core/push_bridge.py`. A registry of live connections plus an HTTP listener on port 8004. |
| `connection.py` | The stock `core/connection.py` with a thirteen line hook added. |
| `connection.py.orig` | The stock file, verbatim, for diffing. |
| `make_patch.py` | Regenerates `connection.py` from `.orig`. |

## The whole change to stock code

Right after `self.websocket = ws` in `handle_connection`, the patched file calls
`push_bridge.register(self)` inside a try block that logs and carries on if
anything goes wrong. Nothing else in the file differs. Check it yourself:

```sh
diff patches/connection.py.orig patches/connection.py
```

## After pulling a newer image

The mounted `connection.py` is a copy of an older version of the file, so a new
image gets its own `connection.py` shadowed by the old one. Re-cut it:

```sh
docker compose down
docker compose pull
docker compose up -d
docker exec cat-server cat /opt/xiaozhi-esp32-server/core/connection.py \
  > patches/connection.py.orig
python3 patches/make_patch.py
docker compose restart
```

`make_patch.py` stops with an error if the anchor line it looks for has moved,
rather than writing a file that silently does nothing.

## The bridge

Port 8004, bound to `0.0.0.0` inside WSL, which Windows reaches at
`127.0.0.1:8004`. It starts on the first connection and does not exist before
one, so a call against it fails until a cat is connected.

| Route | Body | Does |
|---|---|---|
| `GET /devices` | | which cats are connected |
| `POST /face` | `{"emoji": "🤔"}` | change the face |
| `POST /say` | `{"text": "..."}` | speak a sentence out loud |
| `POST /raw` | `{"message": {...}}` | send arbitrary JSON down the socket |

`tools/push.py` wraps all of it, and `tools/fake_cat.py` gives you something to
aim at when the hardware is off.

There is no authentication. That is acceptable on a laptop behind a home router
and is not acceptable on a VPS, so put a token in front of it before moving.

## Two things worth knowing about the protocol

Speech synthesis drops any message whose `sentence_id` does not match the one
the connection is currently on, so `/say` sets `conn.sentence_id` before
queueing. Without that the request succeeds and nothing comes out.

The face is not an image. The firmware draws one of 21 built in faces, chosen by
the emoji the server sends, and anything outside that set is rejected by `/face`
with the list of what is allowed.
