#!/usr/bin/env python3
"""Calls him out, out loud, when his phone says he is at a bubble tea shop.

The phone runs OwnTracks, which posts its location here over Tailscale every
time iOS wakes it. This script looks the spot up against OpenStreetMap, and
when he is standing in a bubble tea shop it emails a trigger to his iCloud
address. An iPhone Shortcut watching for that email turns the volume up and
speaks the line through the phone speaker. The cat is not involved, because
the cat is on his desk and he is not. Setup, including the phone side, is in
docs/callouts.md. Runs on Windows like the other helpers, stdlib only. Start
it detached with .\\cat.ps1 callout.

    py -3.13 tools\\callout.py                     run the listener
    py -3.13 tools\\callout.py --check LAT LON     which shop that spot would
                                                   trigger, sends nothing
    py -3.13 tools\\callout.py --send-test         send the trigger email now

Every callout is written to data/companion.db as kind callout, which is also
how the cooldown survives a restart.
"""

import argparse
import base64
import json
import math
import os
import re
import smtplib
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rituals import DB_PATH, ROOT, log_row, open_db, read_env  # noqa: E402

PORT = 8090

# What the phone speaks lives in the Shortcut, not here. This copy only rides
# along in the email body so the inbox shows what fired.
LINE = ("Look at this sugar addict back at it again with the daily "
        "performative ahh matcha")

# Must match the "Subject contains" filter in the iPhone automation.
SUBJECT = "cat callout"

# He has to be this close to the shop's pin. Indoor GPS drifts 20 to 50
# metres, so much tighter misses real visits and much looser fires on the
# shop next door.
HIT_METERS = 45
# Fixes worse than this are cell tower guesses and would fire on anything.
WORST_ACCURACY = 80
# Once per shop in this window, and never twice inside the global gap, so a
# plaza with three tea shops does not speak three times.
SHOP_COOLDOWN = timedelta(hours=4)
GLOBAL_GAP = timedelta(minutes=45)

# Shops are fetched for a patch around him and reused until he leaves it, so
# OpenStreetMap is asked a few times a day rather than on every report.
AREA_METERS = 1500
REFETCH_AFTER_METERS = 700
REFETCH_AFTER = timedelta(hours=12)
# The main server returns 504 when busy, so a second one is tried after it.
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]

# OpenStreetMap tags most tea shops cuisine=bubble_tea. The names catch the
# chains that were mapped without it.
BRANDS = re.compile(
    r"bubble ?tea|boba|chatime|gong ?cha|sharetea|presotea|the alley|"
    r"tiger sugar|xing fu tang|kung fu tea|coco fresh|real fruit|tsaocaa|"
    r"yi ?fang|machi machi|chagee|ding tea|happy lemon|heytea|milk ?tea|"
    r"matcha|tsujiri",
    re.I,
)

LOG_PATH = os.path.join(ROOT, "data", "callout.log")
# The last patch of shops, so a restart or a busy map server does not leave it
# blind in the place he usually is.
SHOPS_PATH = os.path.join(ROOT, "data", "callout-shops.json")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def log_to_file():
    if sys.stdout.isatty():
        return
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    except Exception:
        pass


def say(msg):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ the map

def meters(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_tea_shop(tags):
    if "bubble_tea" in tags.get("cuisine", "") or tags.get("shop") == "bubble_tea":
        return True
    return bool(BRANDS.search(tags.get("name", "") + " " + tags.get("brand", "")))


def fetch_shops(lat, lon):
    # Asking by name with a regex times the server out, so this pulls every
    # cafe and food place in the patch and filters here.
    around = f"around:{AREA_METERS},{lat},{lon}"
    q = (f'[out:json][timeout:25];('
         f'nwr({around})["amenity"~"^(cafe|fast_food|restaurant|ice_cream)$"];'
         f'nwr({around})["shop"~"^(bubble_tea|beverages|tea)$"];'
         f');out center tags;')
    body = urllib.parse.urlencode({"data": q}).encode()
    for url in OVERPASS:
        try:
            req = urllib.request.Request(
                url, data=body, headers={"User-Agent": "cat-server-callout"})
            with urllib.request.urlopen(req, timeout=40) as r:
                elements = json.load(r).get("elements", [])
            break
        except Exception:
            if url == OVERPASS[-1]:
                raise
    shops = []
    for e in elements:
        tags = e.get("tags", {})
        if not is_tea_shop(tags):
            continue
        c = e.get("center", e)
        if "lat" not in c:
            continue
        shops.append({"id": f'{e["type"]}/{e["id"]}',
                      "name": tags.get("name", "a bubble tea shop"),
                      "lat": c["lat"], "lon": c["lon"]})
    return shops


class Area:
    def __init__(self):
        self.center = None
        self.at = None
        self.shops = []
        try:
            saved = json.load(open(SHOPS_PATH, encoding="utf-8"))
            self.center = tuple(saved["center"])
            self.at = datetime.fromisoformat(saved["at"])
            self.shops = saved["shops"]
        except Exception:
            pass

    def shops_near(self, lat, lon):
        stale = (self.center is None
                 or meters(lat, lon, *self.center) > REFETCH_AFTER_METERS
                 or datetime.now() - self.at > REFETCH_AFTER)
        if stale:
            try:
                self.shops = fetch_shops(lat, lon)
                self.center, self.at = (lat, lon), datetime.now()
                say(f"map: {len(self.shops)} tea shops within {AREA_METERS} m")
                with open(SHOPS_PATH, "w", encoding="utf-8") as f:
                    json.dump({"center": self.center, "at": self.at.isoformat(),
                               "shops": self.shops}, f, ensure_ascii=False)
            except Exception as e:
                # Keep the old patch rather than go blind, and try again on
                # the next report.
                say(f"map lookup failed, keeping the old one: {e}")
        return self.shops

    def closest(self, lat, lon):
        best = None
        for s in self.shops_near(lat, lon):
            d = meters(lat, lon, s["lat"], s["lon"])
            if best is None or d < best[1]:
                best = (s, d)
        return best


# ------------------------------------------------------------------ cooldown

def last_callouts(db):
    rows = db.execute(
        "SELECT ts, data FROM log WHERE kind = 'callout' AND ts >= ? ORDER BY id",
        ((datetime.now() - SHOP_COOLDOWN).isoformat(timespec="seconds"),),
    ).fetchall()
    return [(datetime.fromisoformat(ts), json.loads(data)) for ts, data in rows]


def allowed(db, shop):
    now = datetime.now()
    for ts, data in last_callouts(db):
        if now - ts < GLOBAL_GAP:
            return False
        if data.get("shop_id") == shop["id"]:
            return False
    return True


# ------------------------------------------------------------------ the email

def send_trigger(env, place):
    need = ["CALLOUT_SMTP_HOST", "CALLOUT_SMTP_USER", "CALLOUT_SMTP_PASSWORD", "CALLOUT_TO"]
    missing = [k for k in need if not env.get(k)]
    if missing:
        raise RuntimeError("blank in .env: " + ", ".join(missing))
    msg = EmailMessage()
    msg["From"] = env.get("CALLOUT_FROM") or env["CALLOUT_SMTP_USER"]
    msg["To"] = env["CALLOUT_TO"]
    msg["Subject"] = f"{SUBJECT}: {place}"
    msg.set_content(f"{LINE}\n\n{place}, {datetime.now():%H:%M}")
    port = int(env.get("CALLOUT_SMTP_PORT") or 587)
    if port == 465:
        s = smtplib.SMTP_SSL(env["CALLOUT_SMTP_HOST"], port, timeout=20)
    else:
        s = smtplib.SMTP(env["CALLOUT_SMTP_HOST"], port, timeout=20)
        s.starttls()
    with s:
        s.login(env["CALLOUT_SMTP_USER"], env["CALLOUT_SMTP_PASSWORD"])
        s.send_message(msg)


# ------------------------------------------------------------------ listener

def handle_location(report, area, db, env):
    lat, lon = report.get("lat"), report.get("lon")
    acc = report.get("acc", 9999)
    if lat is None or lon is None:
        return
    if acc > WORST_ACCURACY:
        say(f"report at {lat:.5f},{lon:.5f} too fuzzy ({acc} m), skipped")
        return
    hit = area.closest(lat, lon)
    # Every report gets a line, so a test walk shows the phone is getting
    # through even when nothing fires.
    near = f"{hit[0]['name']} {hit[1]:.0f} m" if hit else "no tea shop mapped"
    say(f"report {lat:.5f},{lon:.5f} +/-{acc} m, closest {near}")
    if hit is None or hit[1] > HIT_METERS:
        return
    shop, dist = hit
    if not allowed(db, shop):
        say(f"at {shop['name']} ({dist:.0f} m) but inside the cooldown")
        return
    try:
        send_trigger(env, shop["name"])
    except Exception as e:
        say(f"at {shop['name']} but the email failed: {e}")
        return
    log_row(db, "callout", LINE, {"shop_id": shop["id"], "shop": shop["name"],
                                  "meters": round(dist), "lat": lat, "lon": lon})
    say(f"called out at {shop['name']} ({dist:.0f} m)")


def make_handler(area, db, env):
    password = env.get("CALLOUT_PASSWORD", "")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, body=b"[]"):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path.rstrip("/") != "/owntracks":
                return self.reply(404)
            if password:
                want = "Basic " + base64.b64encode(f"cat:{password}".encode()).decode()
                if self.headers.get("Authorization") != want:
                    return self.reply(401)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                report = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self.reply(400)
            # OwnTracks waits on this reply, so answer first and look up after.
            self.reply(200)
            if report.get("_type") == "location":
                try:
                    handle_location(report, area, db, env)
                except Exception as e:
                    say(f"report dropped: {e}")

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", nargs=2, type=float, metavar=("LAT", "LON"))
    ap.add_argument("--send-test", action="store_true")
    args = ap.parse_args()
    env = read_env()

    if args.check:
        lat, lon = args.check
        hit = Area().closest(lat, lon)
        if hit is None:
            print("no tea shops mapped nearby")
        else:
            shop, d = hit
            verdict = "would call out" if d <= HIT_METERS else "too far, would stay quiet"
            print(f"closest: {shop['name']}, {d:.0f} m, {verdict}")
        return

    if args.send_test:
        send_trigger(env, "a test from the cat server")
        print(f"sent to {env['CALLOUT_TO']}")
        return

    log_to_file()
    # One request at a time. Reports come minutes apart, and it keeps the
    # cooldown check and the write from racing each other.
    db = open_db(DB_PATH)
    server = HTTPServer(("0.0.0.0", PORT), make_handler(Area(), db, env))
    say(f"listening on port {PORT} for OwnTracks")
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
