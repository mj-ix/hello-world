#!/usr/bin/env python3
"""Phone-friendly live view of the ESP32 nodes, with phone notifications.

Usage:
    python3 presence_web.py
    python3 presence_web.py --watch "1=Hallway:2" --notify

    --watch "1=Hallway:2"   Name board 1 "Hallway" and send an alert when the
                            radar sees someone there for 2 minutes straight.
                            Several: --watch "1=Hallway:2,2=Bathroom:40".
                            Boards not listed get no time-limit alert (right
                            for a bedroom, where lying still for hours is
                            normal).
    --notify                Send alerts to your phone through the free ntfy
                            app (https://ntfy.sh). It prints which channel to
                            subscribe to.
    --port 8000             Web page port.

The board sends its reports straight to this program over WiFi (UDP port
5005), so the page updates within a second or two. Only one program can
listen on that port: stop presence.py and the `npx ... esp32` check first.

The link and the ntfy channel are saved in ~/.ruview-room-sensors.json, so
they stay the same when you restart. Delete that file to get new ones.

Experimental readings from homemade sensors. Not a medical or safety device.
"""
import argparse
import collections
import json
import os
import secrets
import socket
import struct
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

UDP_PORT = int(os.environ.get("RUVIEW_UDP_PORT", 5005))
VITALS_MAGIC = 0xC5110002   # 32-byte vitals packet (firmware edge_vitals_pkt_t)
FUSED_MAGIC = 0xC5110004    # 48-byte vitals + radar packet (edge_fused_vitals_pkt_t)
HISTORY_S = 30 * 60
STALE_S = 20                # page shows "no data" after this
RADAR_GAP_S = 10            # radar dropouts shorter than this don't reset a timer
FALL_COOLDOWN_S = 5 * 60
OFFLINE_S = float(os.environ.get("RUVIEW_OFFLINE_S", 120))
NTFY_URL = os.environ.get("RUVIEW_NTFY_URL", "https://ntfy.sh")
CONFIG = os.path.expanduser(os.environ.get("RUVIEW_CONFIG", "~/.ruview-room-sensors.json"))

_lock = threading.Lock()
_nodes = {}          # node id -> latest state
_history = collections.defaultdict(collections.deque)
_alerts = collections.deque(maxlen=30)
_cfg = {"watch": {}, "notify": False, "topic": None, "key": ""}


# ---------------------------------------------------------------- packets

def parse_packet(buf):
    """Decode a vitals or fused-vitals packet. Returns a dict, or None."""
    if len(buf) < 32:
        return None
    magic = struct.unpack_from("<I", buf, 0)[0]
    if magic not in (VITALS_MAGIC, FUSED_MAGIC):
        return None
    node, flags = buf[4], buf[5]
    motion, presence_score = struct.unpack_from("<ff", buf, 16)
    out = {
        "node": node,
        "present": bool(flags & 1),
        "fall": bool(flags & 2),
        "moving": bool(flags & 4),
        "motion": round(motion, 2),
        "presenceScore": round(presence_score, 2),
        "radar": None,
    }
    if magic == FUSED_MAGIC:
        if len(buf) < 48:
            return None
        dist_cm = struct.unpack_from("<f", buf, 36)[0]
        out["radar"] = {"present": bool(flags & 8),
                        "distanceM": round(dist_cm / 100, 1) if flags & 8 else None}
    return out


# ---------------------------------------------------------------- alerts

def _send_ntfy(title, message, priority):
    if not (_cfg["notify"] and _cfg["topic"]):
        return
    req = urllib.request.Request(
        f"{NTFY_URL}/{_cfg['topic']}", data=message.encode("utf-8"), method="POST",
        headers={"Title": title, "Priority": str(priority), "Tags": "house"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as exc:
        print(f"  ! notification not sent: {exc}", flush=True)


def alert(kind, title, message, priority=4):
    stamp = time.strftime("%H:%M:%S")
    with _lock:
        _alerts.appendleft({"t": round(time.time()), "kind": kind, "title": title, "message": message})
    print(f"[{stamp}] ALERT {title}: {message}", flush=True)
    threading.Thread(target=_send_ntfy, args=(title, message, priority), daemon=True).start()


def board_name(node):
    w = _cfg["watch"].get(node)
    return w["name"] if w else f"Board {node}"


# ---------------------------------------------------------------- state

def _update(pkt, now):
    nid = pkt["node"]
    events = []
    with _lock:
        prev = _nodes.get(nid) or {}
        s = dict(pkt)
        s["seen"] = now
        s["offlineAlerted"] = False
        if prev.get("offlineAlerted"):
            events.append(("back", f"{board_name(nid)} is reporting again", "It's back online.", 3))
        # Radar presence timer, tolerant of short dropouts.
        radar_on = bool(pkt["radar"] and pkt["radar"]["present"])
        since, last_on = prev.get("radarSince"), prev.get("radarLastOn")
        if radar_on:
            if since is None or (last_on is not None and now - last_on > RADAR_GAP_S):
                since = now
            last_on = now
        elif last_on is None or now - last_on > RADAR_GAP_S:
            since = None
        s["radarSince"], s["radarLastOn"] = since, last_on
        s["stillAlerted"] = bool(prev.get("stillAlerted") and since is not None)
        s["lastFallAlert"] = prev.get("lastFallAlert", 0)
        # Rule: someone in a watched spot too long.
        w = _cfg["watch"].get(nid)
        if w and since is not None and not s["stillAlerted"] and now - since >= w["minutes"] * 60:
            s["stillAlerted"] = True
            events.append(("still", f"{w['name']}: someone there for {w['minutes']:g} min",
                           "The radar has seen someone there the whole time. Check on them.", 5))
        # Rule: fall flag (experimental).
        if pkt["fall"] and now - s["lastFallAlert"] > FALL_COOLDOWN_S:
            s["lastFallAlert"] = now
            events.append(("fall", f"{board_name(nid)}: fall flag raised",
                           "Unconfirmed: the board's experimental fall flag went up. Check on them.", 5))
        _nodes[nid] = s
        h = _history[nid]
        h.append((round(now), pkt["present"], pkt["motion"], radar_on if pkt["radar"] else None))
        while h and h[0][0] < now - HISTORY_S:
            h.popleft()
    for kind, title, msg, prio in events:
        alert(kind, title, msg, prio)


def _udp_listener(sock):
    while True:
        buf, _ = sock.recvfrom(4096)
        pkt = parse_packet(buf)
        if pkt:
            _update(pkt, time.time())


def _watchdog():
    while True:
        time.sleep(1)
        now = time.time()
        gone = []
        with _lock:
            for nid, s in _nodes.items():
                if not s["offlineAlerted"] and now - s["seen"] > OFFLINE_S:
                    s["offlineAlerted"] = True
                    gone.append(nid)
        for nid in gone:
            alert("offline", f"{board_name(nid)} stopped reporting",
                  f"No reports for {OFFLINE_S / 60:g} min. Check its power and WiFi.", 4)


def _snapshot():
    now = time.time()
    with _lock:
        nodes = []
        for nid in sorted(_nodes):
            s = _nodes[nid]
            w = _cfg["watch"].get(nid)
            nodes.append({
                "node": nid, "name": board_name(nid),
                "limitMin": w["minutes"] if w else None,
                "present": s["present"], "fall": s["fall"], "motion": s["motion"],
                "radar": s["radar"],
                "radarForS": round(now - s["radarSince"]) if s.get("radarSince") else None,
                "stale": now - s["seen"] > STALE_S, "ageS": round(now - s["seen"]),
                "history": list(_history[nid]),
            })
        return {"now": round(now), "nodes": nodes, "alerts": list(_alerts),
                "notify": bool(_cfg["notify"]), "historyS": HISTORY_S}


# ---------------------------------------------------------------- web page

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Room Sensors</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e2dc;
--on:#1f7a4d;--off:#8a8a84;--move:#c27c0e;--alert:#c0392b;--radar:#2b5fab}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1f1f1d;--ink:#f1f0ec;
--muted:#a3a29c;--line:#33332f;--on:#4cc38a;--off:#7d7c76;--move:#e8a33a;--alert:#ff6b5a;--radar:#7aa7ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.4 -apple-system,system-ui,sans-serif;padding:16px;max-width:560px;margin:auto}
h1{font-size:20px;margin:4px 0 2px}h2{font-size:16px;margin:18px 0 8px}
.sub{color:var(--muted);font-size:13px;margin-bottom:14px}
.banner{border-radius:12px;padding:12px 14px;margin-bottom:12px;font-weight:600;display:none}
.banner.show{display:block}.alert{background:var(--alert);color:#fff}.warn{background:var(--line)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.name{font-weight:600}.age{color:var(--muted);font-size:13px}
.big{font-size:28px;font-weight:700;margin:6px 0 2px}
.on{color:var(--on)}.off{color:var(--off)}.mv{color:var(--move)}.rd{color:var(--radar)}.bad{color:var(--alert)}
.meter{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:6px 0 10px}
.meter i{display:block;height:100%;background:var(--move)}
.kv{display:flex;justify-content:space-between;gap:8px;font-size:15px;padding:3px 0}
.kv span:first-child{color:var(--muted)}
.tl{display:flex;height:22px;border-radius:6px;overflow:hidden;background:var(--line);margin-top:10px}
.tl i{flex:1}.legend{color:var(--muted);font-size:12px;margin-top:4px;display:flex;justify-content:space-between;gap:6px}
.al{border-bottom:1px solid var(--line);padding:8px 0;font-size:14px}.al:last-child{border:0}
.al b{display:block}.al span{color:var(--muted);font-size:12px}
.note{color:var(--muted);font-size:12px;margin-top:18px}
</style></head><body>
<h1>Room Sensors</h1>
<div class="sub" id="sub">Connecting…</div>
<div class="banner alert" id="alertBanner"></div>
<div class="banner warn" id="warnBanner"></div>
<div id="cards"></div>
<h2>Recent alerts</h2>
<div class="card" id="alerts"></div>
<div class="note">Experimental readings from homemade sensors. Not a medical or safety device.</div>
<script>
const QUIET = 3, BUSY = 8;  // WiFi motion-energy bands seen on real hardware (2-20 typical)
const T = new URLSearchParams(location.search).get("t") || "";
const $ = (id) => document.getElementById(id);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function dur(s){return s<60? s+" s" : Math.floor(s/60)+" min "+(s%60)+" s"}
function timeline(h, span, now){
  const bins = 60, out = Array(bins).fill(null);
  for (const [t,p,m,r] of h){ const i = Math.floor((t-(now-span))/span*bins); if(i>=0&&i<bins){
    const here = (r===null||r===undefined) ? p : r;
    const lvl = here ? (m >= BUSY ? 2 : 1) : 0; out[i] = Math.max(out[i]??0, lvl);} }
  const col = ["var(--off)","var(--on)","var(--move)"];
  return out.map(v=>`<i style="background:${v==null?"transparent":col[v]};opacity:${v==null?1:(v?1:.35)}"></i>`).join("");
}
function card(n, span, now){
  // With a radar fitted, the radar alone decides "someone there": it watches
  // only its own area, while WiFi reacts to activity anywhere nearby.
  const who = n.radar ? n.radar.present : n.present;
  const m = n.motion || 0;
  const act = m < QUIET ? ["Quiet","off"] : m < BUSY ? ["Some activity","mv"] : ["Lots of activity","mv"];
  const radar = n.radar ? `<div class="kv"><span>Radar</span><span class="rd">${n.radar.present?`Someone at ${n.radar.distanceM} m`:"Nobody"}</span></div>` : "";
  const over = n.limitMin && n.radarForS >= n.limitMin*60;
  const forS = (n.radarForS!=null && n.radar && n.radar.present) ? `<div class="kv"><span>There for</span><span class="${over?"bad":""}">${dur(n.radarForS)}${n.limitMin?` (alert at ${n.limitMin} min)`:""}</span></div>` : "";
  return `<div class="card">
    <div class="row"><span class="name">${esc(n.name)}</span>
      <span class="age">${n.stale?'<span class="bad">no data for '+dur(n.ageS)+'</span>':'live'}</span></div>
    <div class="big">${who?'<span class="on">Someone there</span>':'<span class="off">Empty</span>'}</div>
    ${radar}${forS}
    <div class="kv"><span>WiFi activity (whole area)</span><span class="${act[1]}">${act[0]} · ${m.toFixed(1)}</span></div>
    <div class="meter"><i style="width:${Math.min(100,m/20*100)}%"></i></div>
    <div class="kv"><span>Fall flag (experimental)</span><span class="${n.fall?"bad":"off"}">${n.fall?"RAISED":"no"}</span></div>
    <div class="tl">${timeline(n.history, span, now)}</div>
    <div class="legend"><span>30 min ago</span><span><b style="color:var(--off);opacity:.5">■</b> empty <b style="color:var(--on)">■</b> there <b style="color:var(--move)">■</b> there, busy</span><span>now</span></div>
  </div>`;
}
async function tick(){
  try{
    const r = await fetch("/api/status?t="+encodeURIComponent(T), {cache:"no-store"});
    if(r.status===403){$("sub").textContent="This link is missing its key. Use the full link printed on the Mac.";return}
    const d = await r.json();
    $("cards").innerHTML = d.nodes.map(n=>card(n, d.historyS, d.now)).join("") ||
      '<div class="card">No boards heard yet. Is the board powered and on WiFi?</div>';
    const recent = d.alerts.filter(a=>d.now-a.t < 10*60 && ["still","fall","offline"].includes(a.kind));
    $("alertBanner").textContent = recent.length ? recent[0].title : "";
    $("alertBanner").classList.toggle("show", recent.length>0);
    const stale = d.nodes.filter(n=>n.stale).map(n=>n.name);
    $("warnBanner").textContent = stale.length ? stale.join(", ")+" stopped reporting." : "";
    $("warnBanner").classList.toggle("show", stale.length>0);
    $("alerts").innerHTML = d.alerts.length ? d.alerts.slice(0,10).map(a=>
      `<div class="al"><b>${esc(a.title)}</b><span>${new Date(a.t*1000).toLocaleString()}</span></div>`).join("")
      : '<span class="off">None yet.</span>';
    $("sub").textContent = "Live · phone alerts "+(d.notify?"on":"off")+" · "+new Date().toLocaleTimeString();
  }catch(e){
    $("sub").textContent = "Can't reach the Mac. Is it awake and on the same WiFi?";
  }
}
tick(); setInterval(tick, 1500);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        given = (parse_qs(url.query).get("t") or [""])[0]
        if url.path == "/":
            # The page itself holds no data; it only fetches with the key.
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif url.path == "/api/status":
            if secrets.compare_digest(given.encode(), _cfg["key"].encode()):
                self._send(200, json.dumps(_snapshot()), "application/json")
            else:
                self._send(403, json.dumps({"error": "missing or wrong key"}), "application/json")
        else:
            self._send(404, "Not found", "text/plain")

    def log_message(self, *args):
        pass


# ---------------------------------------------------------------- setup

def parse_watch(text):
    out = {}
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        try:
            node, rest = part.split("=", 1)
            name, minutes = rest.rsplit(":", 1)
            out[int(node)] = {"name": name.strip() or f"Board {node}", "minutes": float(minutes)}
        except ValueError:
            sys.exit(f'Could not read --watch "{part}". Use the form 1=Hallway:2')
    return out


def load_saved():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(data):
    tmp = CONFIG + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, CONFIG)


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 9))  # no packet is sent; picks the WiFi interface
        return s.getsockname()[0]
    except OSError:
        return "this-mac-ip"
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser(description="Room Sensors phone page and alerts")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--watch", default="", help='e.g. "1=Hallway:2,2=Bathroom:40"')
    ap.add_argument("--notify", action="store_true", help="send alerts to the ntfy phone app")
    args = ap.parse_args()

    saved = load_saved()
    saved.setdefault("key", secrets.token_urlsafe(9))
    saved.setdefault("topic", "room-sensors-" + secrets.token_hex(8))
    save(saved)
    _cfg.update(watch=parse_watch(args.watch), notify=args.notify,
                topic=saved["topic"], key=saved["key"])

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", UDP_PORT))
    except OSError as exc:
        sys.exit(f"Can't listen for the boards on port {UDP_PORT} ({exc}).\n"
                 "Another program is using it: stop presence.py or the `npx ... esp32` check, then retry.")
    threading.Thread(target=_udp_listener, args=(sock,), daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)

    print("Room Sensors is running.\n")
    print("On your phone (same WiFi), open:\n")
    print(f"    http://{_lan_ip()}:{args.port}/?t={_cfg['key']}\n")
    if _cfg["watch"]:
        for nid, w in sorted(_cfg["watch"].items()):
            print(f"Watching board {nid} ({w['name']}): alert if someone is there for {w['minutes']:g} min.")
    else:
        print("No --watch set: no time-limit alerts (fall flag and offline alerts still work).")
    if args.notify:
        print("\nPhone alerts: ON. In the ntfy app, subscribe to this channel:\n")
        print(f"    {_cfg['topic']}\n")
        print("Keep that name private: anyone who knows it can read the alerts.")
        alert("start", "Room Sensors started", "Alerts will arrive here.", 2)
    else:
        print("\nPhone alerts: off (add --notify to turn them on).")
    print("\nThe link and channel stay the same each time. Leave this window open.")
    print("Press Control+C to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
