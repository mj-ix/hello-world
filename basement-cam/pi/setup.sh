#!/usr/bin/env bash
# Raspberry Pi basement camera: Tailscale (secure remote access) + MediaMTX (video server).
# Tested pattern for Raspberry Pi OS Bookworm. Run on the Pi:  sudo bash setup.sh
# Re-running is safe; it upgrades MediaMTX and rewrites the config (keeping the password).
set -euo pipefail

CONF=/usr/local/etc/mediamtx.yml
TS_HOSTNAME="${TS_HOSTNAME:-basement-cam}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-15}"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

echo "==> Checking the camera"
if ! command -v rpicam-hello >/dev/null 2>&1; then
  apt-get update
  apt-get install -y rpicam-apps-lite
fi
if ! rpicam-hello --list-cameras 2>&1 | grep -qE '^[0-9]+ :'; then
  echo "No camera detected." >&2
  echo "Power off, reseat the ribbon cable at both ends (contacts toward the pins), power on, run again." >&2
  exit 1
fi
rpicam-hello --list-cameras 2>&1 | grep -E '^[0-9]+ :'

echo "==> Installing Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

echo "==> Installing MediaMTX"
case "$(uname -m)" in
  aarch64) MTX_ARCH=linux_arm64 ;;
  armv7l)  MTX_ARCH=linux_armv7 ;;
  armv6l)  MTX_ARCH=linux_armv6 ;;
  *) echo "Unsupported CPU: $(uname -m)" >&2; exit 1 ;;
esac
VER=$(curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
      | grep -oP '"tag_name":\s*"\K[^"]+')
[[ -n "$VER" ]] || { echo "Could not look up the latest MediaMTX release" >&2; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL -o "$TMP/mtx.tar.gz" \
  "https://github.com/bluenviron/mediamtx/releases/download/${VER}/mediamtx_${VER}_${MTX_ARCH}.tar.gz"
tar -xzf "$TMP/mtx.tar.gz" -C "$TMP"
systemctl stop mediamtx 2>/dev/null || true
install -m 755 "$TMP/mediamtx" /usr/local/bin/mediamtx
echo "    MediaMTX $VER installed"

echo "==> Writing $CONF"
mkdir -p /usr/local/etc
# Keep an existing viewer password across re-runs; otherwise generate one.
if [[ -z "${VIEW_PASS:-}" && -f "$CONF" ]]; then
  VIEW_PASS=$(sed -n 's/^ *pass: *\([A-Za-z0-9]\{8,\}\) *$/\1/p' "$CONF" | head -n1 || true)
fi
VIEW_PASS="${VIEW_PASS:-$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16)}"

cat >"$CONF" <<YAML
# Basement camera. Anything not listed here keeps MediaMTX's default.
logLevel: info
# Bigger send buffer: stops "reader is too slow, discarding frames" over so-so Wi-Fi.
writeQueueSize: 1024

# Who may do what. The camera source runs inside MediaMTX, so only viewers need a password.
authMethod: internal
authInternalUsers:
  - user: any
    pass:
    ips: ['127.0.0.1', '::1']
    permissions:
      - action: publish
      - action: read
      - action: api
  - user: viewer
    pass: ${VIEW_PASS}
    permissions:
      - action: read
      - action: playback

# Ports (defaults, listed so you know them): RTSP 8554, HLS 8888, WebRTC 8889, playback 9996.
rtsp: true
hls: true
webrtc: true
playback: false          # set to true together with record below

paths:
  cam:
    source: rpiCamera
    rpiCameraWidth: ${WIDTH}
    rpiCameraHeight: ${HEIGHT}
    rpiCameraFPS: ${FPS}
    rpiCameraVFlip: false
    rpiCameraHFlip: false
    rpiCameraBitrate: 2500000
    rpiCameraIDRPeriod: 30
    # Dark basement helpers (uncomment to try):
    # rpiCameraExposure: long
    # rpiCameraGain: 8
    # Keep a rolling 48 hours on the SD card (also set playback: true above):
    # record: true
    # recordPath: /var/lib/basement-cam/%Y-%m-%d_%H-%M-%S-%f
    # recordDeleteAfter: 48h
YAML
mkdir -p /var/lib/basement-cam

echo "==> Installing the mediamtx service"
cat >/etc/systemd/system/mediamtx.service <<'UNIT'
[Unit]
Description=MediaMTX basement camera
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/mediamtx /usr/local/etc/mediamtx.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now mediamtx

echo "==> Disabling Wi-Fi power saving (streams stall with it on)"
if command -v nmcli >/dev/null 2>&1; then
  WIFI_CON=$(nmcli -t -f NAME,TYPE connection show --active 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1; exit}' || true)
  if [[ -n "${WIFI_CON:-}" ]]; then
    nmcli connection modify "$WIFI_CON" wifi.powersave 2 || true
  fi
fi

sleep 2
if ! systemctl is-active --quiet mediamtx; then
  echo "mediamtx failed to start. Last log lines:" >&2
  journalctl -u mediamtx -n 30 --no-pager >&2
  exit 1
fi

LAN_IP=$(hostname -I | awk '{print $1}')
echo
echo "================  Camera is up  ================"
echo "  Login:          user 'viewer'   password '${VIEW_PASS}'"
echo "  On home Wi-Fi:  http://${LAN_IP}:8889/cam    (HLS backup: http://${LAN_IP}:8888/cam)"
echo "  RTSP (VLC):     rtsp://viewer:${VIEW_PASS}@${LAN_IP}:8554/cam"
echo "  Logs:           journalctl -u mediamtx -f"
echo "================================================"
echo

echo "==> Connecting to Tailscale (opens a login link if this Pi is new to your account)"
if tailscale status >/dev/null 2>&1; then
  echo "    Already connected."
else
  tailscale up --hostname="${TS_HOSTNAME}"
fi
TS_IP=$(tailscale ip -4 2>/dev/null || true)
echo
echo "  Away from home (Tailscale app on your phone, signed in to the same account):"
echo "      http://${TS_HOSTNAME}:8889/cam     or     http://${TS_IP:-<tailscale-ip>}:8889/cam"
echo
