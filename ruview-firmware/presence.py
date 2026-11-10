#!/usr/bin/env python3
"""Live, plain-English view of what each ESP32 node is sensing.

Usage:  python3 presence.py            (Control+C to stop)
        python3 presence.py 5          (5-second windows instead of 3)

Every few seconds it asks RuView's reader (`npx @ruvnet/ruview esp32`) for the
latest report from each board and prints one line per board: whether someone
seems to be there, whether they're moving, and the board's fall flag.

These are the board's own experimental estimates, not a medical or safety
device. Test them yourself before relying on them.
"""
import json
import os
import shlex
import subprocess
import sys
import time

# Overridable for testing; normally runs the published RuView CLI.
CMD = shlex.split(os.environ.get("RUVIEW_CMD", "npx --yes @ruvnet/ruview"))


def capture(seconds):
    out = subprocess.run(CMD + ["esp32", "--seconds", str(seconds), "--json"],
                         capture_output=True, text=True, timeout=seconds + 60)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "reason": "unreadable", "detail": (out.stderr or out.stdout)[-300:]}


def bar(value, top, width=10):
    if value is None:
        return " " * width
    filled = max(0, min(width, round(value / top * width)))
    return "#" * filled + "." * (width - filled)


def line_for(node):
    v = node.get("lastVitals")
    nid = node.get("nodeId")
    if not v:
        return f"  board {nid}: connected, waiting for its first sensing report..."
    present = "SOMEONE THERE" if v.get("presence") else "empty"
    moving = "moving" if v.get("motion") else "still"
    score = v.get("presenceScore")
    energy = v.get("motionEnergy")
    text = (f"  board {nid}: {present:<13}  {moving:<6}  "
            f"presence [{bar(score, 20)}] {score:5.1f}  "
            f"motion [{bar(energy, 1)}] {energy:4.2f}")
    if v.get("fall"):
        text += "   <<< FALL FLAG >>>"
    return text


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(f"Listening in {seconds:g}-second windows. Press Control+C to stop.\n")
    while True:
        res = capture(seconds)
        stamp = time.strftime("%H:%M:%S")
        nodes = res.get("nodes") or []
        if not res.get("ok", True) or not nodes:
            why = res.get("reason") or "no boards heard"
            print(f"{stamp}  no data ({why}). Is the board powered and on WiFi?")
            continue
        print(stamp)
        for node in sorted(nodes, key=lambda n: (n.get("nodeId") is None, n.get("nodeId"))):
            print(line_for(node))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
