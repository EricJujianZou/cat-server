#!/usr/bin/env python3
"""Regenerates patches/connection.py from patches/connection.py.orig.

connection.py.orig is a verbatim copy of the file out of the image. This adds
the two-line hook that registers a live connection with the push bridge, and
nothing else. Re-run it after pulling a newer image:

    docker exec cat-server cat /opt/xiaozhi-esp32-server/core/connection.py \
        > patches/connection.py.orig
    python3 patches/make_patch.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, "connection.py.orig")
OUT = os.path.join(HERE, "connection.py")

ANCHOR = """            # 认证通过,继续处理
            self.websocket = ws
"""

INSERT = """            # 认证通过,继续处理
            self.websocket = ws

            # PATCH: register with the push bridge so something outside the
            # server can change this cat's face or make it speak without
            # waiting for the wake word. See patches/README.md. Wrapped so a
            # failure here can never drop a real call.
            try:
                from core import push_bridge

                push_bridge.register(self)
            except Exception as _push_err:
                self.logger.bind(tag=TAG).warning(
                    f"push bridge unavailable: {_push_err}"
                )
"""


def main():
    if not os.path.exists(ORIG):
        sys.exit(
            "patches/connection.py.orig is missing. Copy it out of the image:\n"
            "  docker exec cat-server cat /opt/xiaozhi-esp32-server/core/connection.py"
            " > patches/connection.py.orig"
        )
    src = open(ORIG, encoding="utf-8").read()
    n = src.count(ANCHOR)
    if n != 1:
        sys.exit(
            f"expected the anchor exactly once, found {n}. The image changed, so\n"
            "check core/connection.py by hand before trusting this patch."
        )
    out = src.replace(ANCHOR, INSERT)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    added = len(out.splitlines()) - len(src.splitlines())
    print(f"wrote patches/connection.py, {added} lines added")


if __name__ == "__main__":
    main()
