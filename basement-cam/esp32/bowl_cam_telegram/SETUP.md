# XIAO ESP32S3 Sense bowl camera: every step

Start to finish, for someone who has never flashed an ESP32. Budget about an
hour the first time, most of it waiting for downloads.

## 1. Hardware: how the parts go together

The XIAO ESP32S3 Sense is two boards and an antenna:

- **The main board**, thumbnail-sized, with the USB-C port and two tiny
  buttons on top: **R** (reset) and **B** (boot). Next to the USB port is a
  tiny gold U.FL socket for the antenna.
- **The Sense expansion board**, which carries the camera, a microphone and a
  microSD slot. It plugs onto the back of the main board through a small
  board-to-board connector. If yours arrived separate, line the two
  connectors up and press firmly until it clicks flat. The camera module is a
  small square on a short ribbon, already plugged into the expansion board's
  connector; if the ribbon is loose, lift the connector's dark latch, slide
  the ribbon in with the contacts facing the board, and press the latch down.
- **The antenna**, a small black rectangle on a thin wire. Press its round
  connector onto the U.FL socket with a fingernail until it snaps. It is
  fiddly; it only goes on straight down, not at an angle. Do not skip it, the
  built-in signal is weak and basements are worse.

You also need a **USB-C cable that carries data**. Many cables that came
with gadgets are charge-only; if the board never shows up as a port, the
cable is the first suspect.

## 2. Install the software (once)

1. Install **Arduino IDE 2.x** from arduino.cc/en/software.
2. Open it. **File > Preferences** (Arduino IDE > Settings on a Mac). In
   "Additional boards manager URLs" paste:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   and click OK.
3. **Tools > Board > Boards Manager**. Search `esp32`. Install **esp32 by
   Espressif Systems** (the current 3.x version). It is a large download and
   can take ten minutes.
4. **Sketch > Include Library > Manage Libraries**. Search `ArduinoJson`.
   Install **ArduinoJson by Benoit Blanchon** (version 7.x).

## 3. Create the Telegram bot

1. In Telegram, search for **BotFather** (blue tick) and open the chat.
2. Send `/newbot`. It asks for a display name (anything, like "Bowl cam"),
   then a username that must end in `bot` (like `mikes_bowl_cam_bot`).
3. It replies with a **token** that looks like `1234567890:AAF...`. Copy it.
   Anyone with the token can control the bot, so do not post it anywhere.
4. Tap the link to your new bot and press **Start** so the chat exists. It
   will not answer yet.

## 4. Get the sketch onto your computer

1. Download this repository: on GitHub, **Code > Download ZIP**, then unzip.
2. Find the folder `basement-cam/esp32/bowl_cam_telegram`. Copy that whole
   folder into your Arduino sketchbook, which is `Documents/Arduino` on
   Windows and Mac, `~/Arduino` on Linux. The folder name must stay
   `bowl_cam_telegram`, matching the `.ino` file inside; the IDE insists.
3. Open the IDE: **File > Open**, pick `bowl_cam_telegram.ino`. You see two
   tabs: the sketch and `secrets.h.example`.

## 5. Fill in secrets.h

1. In the folder, copy `secrets.h.example` and name the copy `secrets.h`
   (Windows may hide extensions; make sure it is not `secrets.h.txt`). Reopen
   the sketch so the new tab appears, or use the tab menu's "New Tab" named
   `secrets.h` and paste the example's contents.
2. Edit it:
   - `WIFI_SSID`: your Wi-Fi name, exactly, case matters. It must be a
     **2.4 GHz** network; the ESP32 cannot see 5 GHz networks. If your router
     uses one name for both bands that is fine.
   - `WIFI_PASS`: the Wi-Fi password.
   - `BOT_TOKEN`: the token from BotFather, inside the quotes.
   - `ALLOWED_CHAT_ID`: leave at `0` for now.
3. Save.

## 6. Board settings in the Arduino IDE

Plug the board into the computer. Then in the **Tools** menu:

- **Board > esp32 > XIAO_ESP32S3**
- **Port**: the new entry that appeared when you plugged in. Windows: a
  `COM` number. Mac: `/dev/cu.usbmodem...`. Linux: `/dev/ttyACM0`. If nothing
  appeared, see Troubleshooting.
- **PSRAM: "OPI PSRAM"**. This is the one everybody forgets. Without it the
  camera has nowhere to put pictures and the sketch falls back to a small,
  blurry mode.
- **USB CDC On Boot: Enabled** (it is the default, just check).
- Leave everything else at its default. If an upload ever ends with "Sketch
  too big", set **Partition Scheme** to "Huge APP (3MB No OTA/1MB SPIFFS)".

## 7. Upload

1. Click the round **Upload** arrow at the top left. The bottom pane shows
   compiling (slow the first time, a minute or more), then "Connecting...",
   then "Writing at ..." percentages, then "Hard resetting via RTS pin".
2. If it instead says **"Failed to connect to ESP32-S3: No serial data
   received"**, put the board in bootloader mode by hand: hold **B**, tap
   **R**, release **B**. Click Upload again. After it finishes, tap **R**
   once to start the sketch.

## 8. Watch it start

1. **Tools > Serial Monitor**. Set the speed box to **115200**.
2. Tap **R** on the board so you see the start from the beginning. Expected:

   ```
   bowl-cam starting
   Connecting to YourWifi.....
   Connected. IP 192.168.1.57  signal -61 dBm
   Setting the clock.... done
   Ready. Send /photo to the bot.
   ```

   The signal number matters later: around -50 is excellent, -70 is fine,
   below -80 the uploads will be slow or fail.
3. If you see `Camera init failed` or `PSRAM not found`, go to
   Troubleshooting before continuing.

## 9. Pair the bot with you

1. In Telegram, open your bot's chat and send anything, say `hi`.
2. It replies with your **chat id**, a number like `123456789`.
3. Put that number in `secrets.h`: `#define ALLOWED_CHAT_ID 123456789`
   (no quotes). Save, upload again.
4. When it restarts it messages you: "Bowl cam online...". From now on it
   ignores everyone except you, and it will send alerts to this chat.

## 10. First photo

Send `/photo`. A picture arrives in a few seconds. Send `/help` to see
every command. If it says anything about being unable to reach Telegram,
or nothing arrives, check the Serial Monitor for the HTTP error and see
Troubleshooting.

## 11. Place it at the bowl

- Power it from any USB phone charger with your data cable or any USB-C
  cable; it no longer needs the computer.
- Put the camera **level with the bowl's side window, 30 to 60 cm away,
  facing it squarely**. The window should fill a good part of the picture.
  Blu-Tack, a mini tripod, a 3D-printed clip or a twist tie around a shelf
  leg all work. Keep it out of splash range.
- Add light: a plug-in LED nightlight aimed at the bowl, left on. The board
  has no flash and cannot photograph a dark basement.
- Send `/photo` and `/status` from where you stand to confirm the picture
  and the Wi-Fi signal before you walk away.

## 12. Teach it the water level

1. Send `/aim`. The picture comes back with a small box drawn in the middle.
   Nudge the camera until the window's **low line** (where you want the
   alert) runs through the box and the box shows only window. Repeat `/aim`
   until it is right, then stop touching the camera.
2. With water above the line, send `/calibrate full`.
3. With water below the line (scoop some out, or wait a day), send
   `/calibrate low`. It replies with how different the two looks are. If it
   says "not much", adjust the light or angle and redo both.
4. Refill the bowl. Send `/level` any time to see what it thinks. From now
   on it checks every two minutes on its own and messages you with a photo
   when the water has been below the line for three checks in a row.

## 13. Troubleshooting

- **No port appears when plugged in.** Try another cable (data, not
  charge-only) and another USB socket. On Linux add yourself to the
  `dialout` group and log out and in. If the board shows up only while you
  hold **B** during plug-in, it is in bootloader mode; upload, then tap R.
- **"Failed to connect" on upload.** Hold B, tap R, release B, upload again.
- **`Camera init failed`.** Unplug power. Check the Sense expansion board
  is pressed fully onto the main board and the camera ribbon is seated and
  latched. Check Tools > PSRAM is "OPI PSRAM". Plug back in.
- **`PSRAM not found`.** Tools > PSRAM was not set to "OPI PSRAM". Set it,
  upload again.
- **Never connects to Wi-Fi.** The network must be 2.4 GHz. Name and
  password are case-sensitive. Guest networks with a login web page and
  office networks that ask for a username will not work.
- **Connects to Wi-Fi but Telegram calls fail (HTTP -1 in the monitor).**
  Some routers' "parental" or "secure DNS" features block Telegram; test
  from a phone on the same Wi-Fi. If Telegram has changed its certificate
  authority, set `VERIFY_TLS` to `false` at the top of the sketch as a test;
  if that fixes it, say so and the pinned certificate can be updated. A
  "No answer from NTP" line in the monitor is harmless.
- **Photos are dark or grainy.** More light. The low-light mode only
  stretches what is there.
- **Photos take a long time or fail.** Weak Wi-Fi. Check `/status`; below
  about -80 dBm move the board, the router, or set `FRAME_SIZE` to
  `FRAMESIZE_HD` for smaller uploads.
- **It says "unsure" a lot in `/level`.** The two calibrated looks are too
  similar. Improve the light, make sure the box shows only the window, or
  put a dark card behind a clear window. Or switch to the liquid sensor
  described in the README.
- **It alerted but the bowl is fine.** Something changed in the box: the
  nightlight moved, the bowl moved, a different bowl. Re-aim and
  recalibrate. Alerts need three low checks in a row, so a passing cat does
  not cause them.
- **I changed Wi-Fi or router.** Edit `secrets.h`, upload again. The bot
  token and chat id do not change.
