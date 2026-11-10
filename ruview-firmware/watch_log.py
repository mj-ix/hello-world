#!/usr/bin/env python3
"""Show an ESP32's startup log over USB, reconnecting if the port drops.

Usage:  python3 watch_log.py PORT [SECONDS]
        python3 watch_log.py /dev/cu.usbmodem1101

Press the board's RESET button (or unplug and replug it) after starting this,
so the log begins from the top. Stops after SECONDS (default 40) or Control+C.
Lines about WiFi, the target address and errors are marked with ">>".
"""
import sys
import time

import serial

KEYWORDS = ("wifi", "ssid", "got ip", "target_ip", "target_port", "disconnected",
            "reason=", "not connected", "nvs", "error", "fail", "csi", "udp")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    port = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
    end = time.monotonic() + seconds
    print(f"Watching {port} for {seconds:.0f} s. Press RESET on the board now.\n")
    ser = None
    lines = 0
    while time.monotonic() < end:
        if ser is None:
            try:
                # dsrdtr/rtscts off and no DTR/RTS toggling: just listen, never
                # put the board into download mode.
                ser = serial.Serial()
                ser.port = port
                ser.baudrate = 115200
                ser.timeout = 0.5
                ser.dtr = False
                ser.rts = False
                ser.open()
            except (serial.SerialException, OSError):
                ser = None
                time.sleep(0.3)
                continue
        try:
            raw = ser.readline()
        except (serial.SerialException, OSError):
            print("   (board reconnecting...)")
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            continue
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace").rstrip()
        # Strip ANSI colour codes the firmware adds.
        clean = "".join(text.split("\x1b[")[0:1]) + "".join(
            part.split("m", 1)[-1] for part in text.split("\x1b[")[1:])
        mark = ">> " if any(k in clean.lower() for k in KEYWORDS) else "   "
        print(mark + clean)
        lines += 1
    if ser is not None:
        ser.close()
    print(f"\nDone ({lines} lines).")
    if lines == 0:
        print("Nothing was received. Check the port name, and try pressing RESET while this runs.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
