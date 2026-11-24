# Basement camera you can check from anywhere

Two boards on the table, one basement, and one question to answer from your
phone: is there water in the cats' bowl? This folder has three working setups.
Start with the first one; the other two are there if you later want live video.

## Start here: a photo of the water bowl on demand

**Use the XIAO ESP32S3 Sense with the Telegram sketch**
(`esp32/bowl_cam_telegram/`). You send `/photo` to a Telegram bot you own, the
board takes a 1600x1200 picture and sends it back, from anywhere, in a few
seconds. Nothing is opened on your router, no Pi is needed, and the whole thing
runs from any USB phone charger next to the bowl. A live stream would be
overkill for this, and it is the live stream that makes remote access hard.

### Set it up (about 20 minutes)
The short version is below. The long version, with every click, button and
error message, is in `esp32/bowl_cam_telegram/SETUP.md`.

1. In Telegram, message **@BotFather**, send `/newbot`, follow the prompts, and
   copy the token it gives you. Only people who know the token can drive the
   bot, and the sketch additionally answers only your own chat id.
2. Arduino IDE 2.x. Boards Manager: **esp32 by Espressif Systems**. Library
   Manager: **ArduinoJson** (Benoit Blanchon, 7.x). Board **XIAO_ESP32S3**,
   Tools > **PSRAM: "OPI PSRAM"** (mandatory), **USB CDC On Boot: Enabled**.
3. Screw the antenna onto the board. Basements eat 2.4 GHz signal.
4. In `esp32/bowl_cam_telegram/`, copy `secrets.h.example` to `secrets.h`, fill
   in Wi-Fi and the bot token, leave `ALLOWED_CHAT_ID` at 0, upload.
5. Message your bot anything. It replies with your chat id. Put that number in
   `secrets.h`, upload again. From now on it ignores everyone but you.
6. Send `/photo`. `/status` reports Wi-Fi signal, uptime and the last level check.

Set `AUTO_PHOTO_MINUTES` in the sketch (for example 720) to also get a picture
twice a day without asking. Commands sent while the board was unplugged are
discarded on boot, so you never get a pile of stale photos.

### Low-water alert
The same sketch watches the bowl and messages you, with a photo, when the
water drops below your line, then again when it is back. It checks every two
minutes and needs three low readings in a row before it alerts, so a cat's
head in the way does not trigger it. While the bowl stays low it reminds you
every eight hours. Two ways to sense the level; pick one with `LEVEL_SOURCE`
at the top of the sketch.

**With the camera, no extra parts (`LEVEL_CAMERA`, the default).** It watches
a small box in the middle of the picture. Line the box up with your bowl's
level window at the point you call "low", then teach it what the box looks
like with water and without:

1. Send `/aim`. You get a picture with the box drawn on it. Move the camera
   until the window's low line runs through the box, and the box shows only
   window (not the bowl's edge or the floor). Repeat until it looks right.
2. With water above the line, send `/calibrate full`.
3. With water below the line (scoop some out, or wait), send `/calibrate low`.
   It tells you how different the two looks are; if it says "not much", change
   the light or the angle and do both steps again.
4. Refill. `/level` shows what it thinks right now and the numbers behind it.

It compares the box to the rest of the frame, so a brighter or dimmer room
does not fool it, but it needs *some* light: it refuses to judge in the dark
rather than guess. The nightlight from the next section covers that. Clear
water against a plain window can be a subtle change; a coloured or frosted
window, or a dark card behind a clear one, makes it much more reliable.

**With a liquid sensor, about $5 (`LEVEL_SENSOR_PIN`).** An XKC-Y25-NPN
non-contact liquid level sensor is a flat puck you tape to the *outside* of
the bowl at your line. It senses water through up to about 2 cm of plastic,
ceramic or glass (not metal), does not care about light or cats, and needs no
calibration. Wiring to the XIAO: brown to the 5V pin, blue to GND, yellow to
D1. If yours has a fourth (black) wire, leave it unconnected. Get the NPN
version specifically; the "-V" version outputs 5 V on its signal wire, which
the ESP32's pins cannot take. Set `LEVEL_SOURCE` to `LEVEL_SENSOR_PIN`,
upload, and check `/level` with water above and below the line; if it reads
backwards, flip `SENSOR_WET_LEVEL`. The small screw on the sensor's back sets
sensitivity if it is sluggish through a thick wall.

If you want this to just work, buy the sensor. If you want to try with what
is on the table today, start with the camera; the sensor is a one-line change
later and the photos keep working either way.

### About the Adafruit CLUE
The CLUE has no camera. The sensor on its front is an APDS9960 light, colour,
gesture and proximity sensor, next to two white LEDs. Its proximity sensing
bounces infrared off nearby objects a few centimetres away, and water hardly
reflects infrared, so pointed at a bowl it reads almost nothing. It also has
Bluetooth only, no Wi-Fi, so it could not send you an alert without a phone
sitting beside it. Keep it for another project; its other sensors are
pressure, temperature, humidity, motion, compass and a microphone.

### Making the water level actually visible
This matters more than anything in the code, for the photos and for the
watcher. Water is transparent, and a camera looking straight down into a bowl
cannot tell full from nearly empty. Your bowl's side window solves most of
this: point the camera square at the window, close enough that the window
fills a good part of the frame.

- **Angle.** Mount the camera low, about at the height of the bowl rim, 30 to
  60 cm away, looking slightly down across the bowl. The water line shows up
  against the far inside wall. Straight-down views hide it.
- **Bowl.** A light, matte interior (plain white ceramic) shows the wet/dry
  line best. Mirror-like stainless steel and clear glass are the hardest to
  read; a clear bowl works only with a dark card behind it.
- **Reference.** A bowl with a visible ring or step inside gives you a
  built-in gauge. Otherwise take photos at full, half and empty once; after
  that you will read it at a glance.
- **Light.** The board has no flash and the basement will be dark. A plug-in
  LED nightlight pointed at the bowl is enough and costs almost nothing. The
  sketch's low-light mode helps but cannot photograph a black room.
- **Test before mounting.** Fill the bowl to three different levels, take a
  `/photo` of each, and adjust the angle until the three are obviously
  different.

---

## If you later want live video

## Which board to use

| | Raspberry Pi + ribbon camera | XIAO ESP32S3 Sense |
|---|---|---|
| Video | H.264, 720p–1080p, smooth | MJPEG, 800x600–1280x720, ~10–15 fps |
| Viewers at once | Many | Realistically one |
| Remote access | Easy and safe (Tailscale runs on the Pi) | Needs a helper device or a push-to-cloud trick |
| Low light | NoIR camera + IR light works well | Poor; needs a light left on |
| Extras later | Recording, motion alerts, Home Assistant | Snapshots to microSD |
| Power / size | 2–5 W, needs a case and a good PSU | 0.5 W, thumb-sized, any USB charger |

**For live video, use the Raspberry Pi if you have a Pi board for that camera**
(Zero 2 W or newer). The deciding factor is remote access. Tailscale on the Pi
gives you a private, encrypted link from your phone to the camera with no port
forwarding, no dynamic DNS, no exposed services. The ESP32 cannot run anything
like that, so a stream that is "live from anywhere" needs another always-on
device at home or an insecure port-forward.

Use the ESP32 stream sketch if you only need live video while on your home
Wi-Fi, or as a second tiny camera later.

---

## Option A: Raspberry Pi live stream

### What you need
- A Pi with a camera connector: Zero 2 W, 3, 4 or 5. Pi 5 and all Zero models
  use the small 22-pin connector, so check the ribbon cable fits your board.
- Raspberry Pi OS **Bookworm** or **Trixie** (64-bit preferred), flashed with Raspberry Pi
  Imager. In the Imager's settings, set a hostname, your Wi-Fi, and enable SSH.
- The camera module, ribbon cable seated at both ends with the contacts facing
  the right way (blue tab away from the board on most connectors).
- A Tailscale account (free for personal use) and the Tailscale app on your phone.

### Install
SSH into the Pi, copy `pi/setup.sh` over (or paste it into a file), then:

```bash
sudo bash setup.sh
```

The script:
1. Checks that the camera is detected (`rpicam-hello --list-cameras`).
2. Installs Tailscale.
3. Downloads the latest MediaMTX for your Pi's CPU and installs it as a
   systemd service that starts on boot.
4. Writes a MediaMTX config that reads the camera directly at 1280x720, 15 fps,
   with a random viewer password it prints at the end.
5. Turns off Wi-Fi power saving so the stream does not stall.
6. Runs `tailscale up`, which prints a login link. Open it, approve the device.

### Watch it
- On home Wi-Fi: `http://<pi-ip>:8889/cam` (WebRTC, lowest latency).
- Away from home, with Tailscale on your phone: `http://basement-cam:8889/cam`
  or `http://<tailscale-ip>:8889/cam`.
- If WebRTC will not connect on some network, use the HLS page on port 8888
  instead: `http://basement-cam:8888/cam`.
- RTSP for VLC or a NAS: `rtsp://basement-cam:8554/cam`.

Username is `viewer`, password is the one the script printed. It is also saved
in `/usr/local/etc/mediamtx.yml` on the Pi.

### Tuning
Edit `/usr/local/etc/mediamtx.yml` on the Pi, then `sudo systemctl restart mediamtx`.

- Upside-down mount: set `rpiCameraVFlip: true` and `rpiCameraHFlip: true`.
- Sharper picture: `rpiCameraWidth: 1920`, `rpiCameraHeight: 1080`. Keep FPS at
  15 or lower on a Zero 2 W.
- Dark basement: `rpiCameraExposure: long` and `rpiCameraGain: 8` help, but a
  camera cannot see without light. See "Lighting" below.
- Keep the last two days on the SD card: uncomment the `record:` lines in the
  config. Playback is at `http://basement-cam:9996/list?path=cam`.

### If the picture freezes after a few minutes
That is Wi-Fi, not the camera. MediaMTX logs `reader is too slow, discarding
frames` when the link cannot carry the stream. The config already raises the
send buffer (`writeQueueSize: 1024`); beyond that, lower `rpiCameraBitrate`
to `1500000`, drop to 800x600, or move the Pi or router closer.

### If the camera source misbehaves
MediaMTX's built-in Pi camera reader depends on the system `libcamera` package
matching the MediaMTX build. After a big `apt upgrade`, run `setup.sh` again to
get a matching MediaMTX. If it still logs "camera not available", switch the
path to this fallback, which uses the Pi's own `rpicam-vid` and `ffmpeg`
(`sudo apt install ffmpeg`):

```yaml
paths:
  cam:
    runOnInit: >
      bash -c 'rpicam-vid -t 0 -n --width 1280 --height 720 --framerate 15
      --inline -o - | ffmpeg -hide_banner -loglevel error -f h264 -i -
      -c copy -f rtsp rtsp://localhost:$RTSP_PORT/$MTX_PATH'
    runOnInitRestart: true
```

---

## Option B: XIAO ESP32S3 Sense live stream (home Wi-Fi)

### Flash it
1. Arduino IDE 2.x. Boards Manager: install **esp32 by Espressif Systems**
   (3.x is fine; if the camera fails to init, 2.0.17 is the known-good fallback).
2. Board: **XIAO_ESP32S3**. Tools menu: **PSRAM: "OPI PSRAM"** (mandatory, the
   camera has nowhere to put frames otherwise), **USB CDC On Boot: Enabled**.
3. Screw the Wi-Fi antenna onto the U.FL connector. Basements eat 2.4 GHz
   signal, and this board is 2.4 GHz only.
4. In `esp32/basement_cam/`, copy `secrets.h.example` to `secrets.h` and fill in
   Wi-Fi name, Wi-Fi password, and a camera username and password.
5. Open `basement_cam.ino`, upload. Serial Monitor at 115200 prints the address.
6. Open `http://basement-cam.local/` (or the printed IP). Log in. You get a live
   MJPEG view, a `/jpg` snapshot link, and a `/status` JSON page with Wi-Fi
   signal and uptime.
7. In your router, reserve the ESP32's DHCP lease so the IP never changes.

Settings at the top of the sketch: frame size, JPEG quality, flip, and a
low-light mode that raises sensor gain (grainier but visible).

### Getting to it from outside the house
The sketch serves plain HTTP with basic auth. That is fine on your LAN and
**not** something to forward from the internet. Pick one:

- **Tailscale subnet router (best).** Any always-on Linux box, NAS or Pi at
  home runs `tailscale up --advertise-routes=192.168.1.0/24` (your LAN's
  subnet), you approve the route in the Tailscale admin console, and your phone
  reaches `http://<esp32-ip>/` through the tunnel. Some routers (GL.iNet,
  OpenWrt, UniFi, Synology) can run Tailscale themselves.
- **Snapshot on demand via a Telegram bot.** That is the `bowl_cam_telegram`
  sketch at the top of this file: no inbound connection and no helper device,
  but stills rather than a stream.
- **No always-on device and you want live video from anywhere:** that is the
  case for Option A.

---

## All options: things that matter more than the board

- **Lighting.** A basement at night is black to either camera. Options, cheapest
  first: leave a low-wattage LED bulb on, a smart bulb you switch on from the
  same phone before you look, a motion-activated LED, or (Pi only) a NoIR
  camera module plus an 850 nm IR illuminator for true night vision.
- **Wi-Fi.** Test signal where the camera will live before mounting it. Both
  boards report signal strength (`/status` on the ESP32, `iw dev wlan0 link` on
  the Pi). Under about -75 dBm the stream will stutter. Ethernet to the Pi
  beats everything if there is a drop nearby.
- **Power.** Use a proper 5 V supply (official Pi PSU for a Pi 4/5). Brownouts
  corrupt SD cards. A cheap smart plug lets you power-cycle a hung camera
  remotely.
- **Humidity.** Basements are damp. A vented case or a small enclosure keeps
  condensation off the lens and the board.
