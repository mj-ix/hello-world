#!/usr/bin/env python3
"""Phone-friendly live view of the ESP32 nodes, served from this Mac.

Usage:  python3 presence_web.py            (Control+C to stop)
        python3 presence_web.py 8080       (use a different port)

It prints a link. Open that link on a phone that's on the same WiFi. The link
contains a secret key; without it the page shows nothing, so other people on
the WiFi can't see it. Keep the Mac awake while it runs (see the guide).

Uses the same reader as presence.py (`npx @ruvnet/ruview esp32 --json`). The
values are the boards' own experimental estimates, not a medical or safety
device.
"""
import collections
import json
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import presence  # capture() lives there; same folder

WINDOW_S = 3
HISTORY_S = 30 * 60
STALE_S = 20
TOKEN = secrets.token_urlsafe(9)

_lock = threading.Lock()
_state = {"updated": None, "error": None, "nodes": {}}
_history = collections.defaultdict(collections.deque)  # node -> (t, present, moving, radar)


def _summarise(node):
    v = node.get("lastVitals") or {}
    out = {
        "node": node.get("nodeId"),
        "hasVitals": bool(v),
        "present": bool(v.get("presence")),
        "moving": bool(v.get("motion")),
        "motion": v.get("motionEnergy"),
        "presenceScore": v.get("presenceScore"),
        "fall": bool(v.get("fall")),
        "rateHz": node.get("csiRateHz"),
        "radar": None,
    }
    if "mmwavePresent" in v:
        out["radar"] = {"present": bool(v.get("mmwavePresent")),
                        "distanceM": round((v.get("mmwaveDistanceCm") or 0) / 100, 1)}
    return out


def _collector():
    while True:
        try:
            res = presence.capture(WINDOW_S)
        except Exception as exc:  # keep running whatever happens
            res = {"ok": False, "reason": str(exc)[:200]}
        now = time.time()
        nodes = res.get("nodes") or []
        with _lock:
            if not res.get("ok", True) or not nodes:
                _state["error"] = res.get("reason") or "no boards heard"
                continue
            _state["error"] = None
            _state["updated"] = now
            for n in nodes:
                s = _summarise(n)
                s["seen"] = now
                _state["nodes"][s["node"]] = s
                h = _history[s["node"]]
                radar = s["radar"]["present"] if s["radar"] else None
                h.append((round(now), s["present"], round(s["motion"] or 0, 1), radar))
                while h and h[0][0] < now - HISTORY_S:
                    h.popleft()


def _snapshot():
    now = time.time()
    with _lock:
        nodes = []
        for nid, s in sorted(_state["nodes"].items(), key=lambda kv: (kv[0] is None, kv[0])):
            item = dict(s)
            item["stale"] = now - s["seen"] > STALE_S
            item["ageS"] = round(now - s["seen"])
            item["history"] = list(_history[nid])
            nodes.append(item)
        return {"now": round(now), "error": _state["error"], "nodes": nodes,
                "historyS": HISTORY_S}


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
h1{font-size:20px;margin:4px 0 2px}.sub{color:var(--muted);font-size:13px;margin-bottom:14px}
.banner{border-radius:12px;padding:12px 14px;margin-bottom:12px;font-weight:600;display:none}
.banner.show{display:block}.alert{background:var(--alert);color:#fff}
.warn{background:var(--line)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.name{font-weight:600}.age{color:var(--muted);font-size:13px}
.big{font-size:28px;font-weight:700;margin:6px 0 2px}
.on{color:var(--on)}.off{color:var(--off)}.mv{color:var(--move)}.rd{color:var(--radar)}
.fall{color:var(--alert)}
.meter{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:6px 0 10px}
.meter i{display:block;height:100%;background:var(--move)}
.kv{display:flex;justify-content:space-between;font-size:15px;padding:3px 0}
.kv span:first-child{color:var(--muted)}
.tl{display:flex;height:22px;border-radius:6px;overflow:hidden;background:var(--line);margin-top:10px}
.tl i{flex:1}.legend{color:var(--muted);font-size:12px;margin-top:4px;display:flex;justify-content:space-between}
.note{color:var(--muted);font-size:12px;margin-top:18px}
</style></head><body>
<h1>Room Sensors</h1>
<div class="sub" id="sub">Connecting…</div>
<div class="banner alert" id="fallBanner">Fall flag raised. Check on them.</div>
<div class="banner warn" id="warnBanner"></div>
<div id="cards"></div>
<div class="note">Experimental readings from homemade sensors. Not a medical or safety device.</div>
<script>
const QUIET = 3, BUSY = 8;  // WiFi motion-energy bands seen on real hardware (2-20 typical)
const T = new URLSearchParams(location.search).get("t") || "";
const $ = (id) => document.getElementById(id);
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function timeline(h, span, now){
  const bins = 60, out = Array(bins).fill(null);
  for (const [t,p,m,r] of h){ const i = Math.floor((t-(now-span))/span*bins); if(i>=0&&i<bins){
    const here = (r===null||r===undefined) ? p : r;
    const lvl = here ? (m >= BUSY ? 2 : 1) : 0; out[i] = Math.max(out[i]??0, lvl);} }
  const col = ["var(--off)","var(--on)","var(--move)"];
  return out.map(v=>`<i style="background:${v==null?"transparent":col[v]};opacity:${v==null?1:(v?1:.35)}"></i>`).join("");
}
function card(n, span, now){
  // The radar watches only its own area; WiFi sensing reacts to activity
  // anywhere between the board and the router, so with a radar fitted the
  // radar alone decides "someone there".
  const who = n.radar ? n.radar.present : n.present;
  const m = n.motion || 0;
  const act = m < QUIET ? ["Quiet","off"] : m < BUSY ? ["Some activity","mv"] : ["Lots of activity","mv"];
  const status = !n.hasVitals ? '<span class="off">Waiting…</span>'
    : who ? '<span class="on">Someone there</span>' : '<span class="off">Empty</span>';
  const motion = Math.max(0, Math.min(100, (n.motion||0)/20*100));
  const radar = n.radar ? `<div class="kv"><span>Radar</span><span class="rd">${n.radar.present?`Someone at ${n.radar.distanceM} m`:"Nobody"}</span></div>` : "";
  return `<div class="card">
    <div class="row"><span class="name">Board ${esc(n.node)}</span>
      <span class="age">${n.stale?'<span class="fall">no data for '+n.ageS+' s</span>':'updated '+n.ageS+' s ago'}</span></div>
    <div class="big">${status}</div>
    <div class="kv"><span>WiFi activity (whole area)</span><span class="${act[1]}">${act[0]} · ${m.toFixed(1)}</span></div>
    <div class="meter"><i style="width:${motion}%"></i></div>
    ${radar}
    <div class="kv"><span>Fall flag</span><span class="${n.fall?"fall":"off"}">${n.fall?"RAISED":"no"}</span></div>
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
    $("fallBanner").classList.toggle("show", d.nodes.some(n=>n.fall && !n.stale));
    const stale = d.nodes.filter(n=>n.stale).length;
    const w = d.error && !d.nodes.length ? "Not hearing any boards ("+d.error+")."
            : stale ? stale+" board(s) stopped reporting." : "";
    $("warnBanner").textContent = w; $("warnBanner").classList.toggle("show", !!w);
    $("sub").textContent = "Live · refreshes every 3 s · "+new Date().toLocaleTimeString();
  }catch(e){
    $("sub").textContent = "Can't reach the Mac. Is it awake and on the same WiFi?";
  }
}
tick(); setInterval(tick, 3000);
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
        authed = secrets.compare_digest(given, TOKEN)
        if url.path == "/":
            # The page itself holds no data; it only fetches with the key.
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif url.path == "/api/status":
            if not authed:
                self._send(403, json.dumps({"error": "missing or wrong key"}), "application/json")
            else:
                self._send(200, json.dumps(_snapshot()), "application/json")
        else:
            self._send(404, "Not found", "text/plain")

    def log_message(self, *args):  # keep the Terminal quiet
        pass


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
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    threading.Thread(target=_collector, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Room Sensors page is running.\n")
    print("On your phone (same WiFi), open:\n")
    print(f"    http://{_lan_ip()}:{port}/?t={TOKEN}\n")
    print("The key at the end changes every time you start this, so the old link")
    print("stops working. Leave this window open. Press Control+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
