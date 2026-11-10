# RuView firmware for my ESP32 boards

This folder holds ready-made software ("firmware") for the little ESP32 boards.
Once a board has it, the board joins your home WiFi and sends WiFi-sensing data
to your MacBook.

**Status:** the ESP32-C6 build has run on a real Waveshare ESP32-C6-LCD-1.47:
it booted, joined home WiFi, and streamed WiFi-sensing data to the Mac
(2026-11-10). The S3 builds haven't been tried on a board yet.

**Tip:** if a board won't join the WiFi (the log shows `reason=2` or
`reason=201`), move it closer to the router. Its small antenna needs a decent
signal. `python3 watch_log.py $PORT` shows the board's startup log.

---

# Step-by-step guide for a MacBook Air (no experience needed)

Go slowly and do the steps in order. Steps 1–3 are only done once.

**You'll need:**
- The MacBook Air, plugged in and connected to your home WiFi
- One ESP32 board. Start with the **Waveshare ESP32-C6** (the one with the
  1.47" screen): it's the type RuView has confirmed works.
- A **USB-C to USB-C cable that carries data**. Some cables only charge; if the
  board isn't found in step 5, try a different cable. (Older MacBook Airs with
  rectangular USB-A ports need a USB-A to USB-C cable instead.)
- Your home WiFi name and password

**Words you'll see:**
- **Terminal:** a window where you type commands. You paste a line, press
  **Return**, and wait until it finishes and you can type again.
- **Paste:** press **⌘ + V** (Command and V together).

---

## Step 1: Install two free programs

1. **Python:** open Safari and go to <https://www.python.org/downloads/>.
   Click the yellow **Download Python** button. When it finishes, click the
   download arrow at the top right of Safari and open the file. Click
   **Continue** and **Agree** through the screens, then **Install**, and type
   your Mac password when asked. When a Finder window pops up at the end, you
   can close it.
2. **Node.js:** go to <https://nodejs.org/>, click the button marked **LTS**,
   open the downloaded file, and click **Continue** / **Agree** / **Install**
   the same way.

## Step 2: Download the firmware

1. Make sure you're signed in to GitHub in Safari, then open this link:
   <https://github.com/mj-ix/hello-world/archive/refs/heads/ccr-cbf88bb5-osmutu.zip>
2. Safari downloads it and unzips it into your **Downloads** folder as a folder
   called **hello-world-ccr-cbf88bb5-osmutu**. You don't need to open it.

## Step 3: Open Terminal and install the board tools

1. Press **⌘ + Space**, type `terminal`, and press **Return**. A window opens.
   Keep it open for every step below.
2. Paste this line and press Return:

   ```
   python3 --version
   ```

   It should say **Python 3.** followed by numbers. (If a box pops up asking to
   install "command line developer tools", click **Cancel**, quit Terminal with
   **⌘ + Q**, open it again, and retry. The Python installer needs a fresh
   Terminal window.)
3. Make a private folder for the board tools (a "virtual environment"), so they
   don't interfere with anything else on the Mac. Paste these two lines one at a
   time, pressing Return after each:

   ```
   python3 -m venv ~/ruview-env
   ```
   ```
   source ~/ruview-env/bin/activate
   ```

   Your Terminal line now starts with **(ruview-env)**.
4. Paste this line and press Return:

   ```
   python3 -m pip install "esptool>=5.0" esp-idf-nvs-partition-gen pyserial
   ```

   Text scrolls for a minute. It's done when it says
   **Successfully installed…**

## Step 4: Each time you open Terminal

**Do this every time you open a new Terminal window**, before the steps below.
Paste these two lines one at a time, pressing Return after each:

```
source ~/ruview-env/bin/activate
```
```
cd ~/Downloads/hello-world-ccr-cbf88bb5-osmutu/ruview-firmware
```

Your Terminal line should start with **(ruview-env)**. If later steps say
`No module named esptool`, you skipped the first line; run it and try again.

## Step 5: Plug in the board and let the Mac find it

1. Plug the ESP32-C6 into the MacBook with the cable.
2. If the Mac asks **"Allow accessory to connect?"**, click **Allow**.
3. Paste this and press Return:

   ```
   PORT=$(ls /dev/cu.usbmodem* | head -1); echo "Board found at: $PORT"
   ```

   It should say something like **Board found at: /dev/cu.usbmodem1101**.

   *If it says `no matches found` or shows nothing after "found at":* the Mac
   can't see the board. Try a different cable. If that doesn't help, hold the
   small **BOOT** button on the board while plugging it in, then run the line
   again.

**Only plug in one board at a time**, so the Mac finds the right one.

## Step 6: Put the firmware on the board ("flashing")

Paste this whole line and press Return:

```
cd esp32c6-4mb && python3 -m esptool --chip esp32c6 --port $PORT --baud 460800 write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB 0x0 bootloader.bin 0x8000 partition-table.bin 0xf000 ota_data_initial.bin 0x20000 esp32-csi-node.bin; cd ..
```

You'll see percentages climbing. It's done when it says
**Hash of data verified** and **Hard resetting**.

*If it says it can't connect:* hold the **BOOT** button, tap **RESET** (or
unplug and replug), let go of BOOT, and run the line again.

## Step 7: Give the board your WiFi details

1. Paste this and press Return. It finds your Mac's address on your home
   network:

   ```
   IP=$(ipconfig getifaddr en0); echo "This Mac is at: $IP"
   ```

   It should say something like **This Mac is at: 192.168.1.20**.
2. Copy the line below, but **change `MyHomeWiFi` to your WiFi's name** (keep
   the quote marks). Then press Return:

   ```
   python3 provision.py --port $PORT --ssid "MyHomeWiFi" --target-ip $IP --node-id 1 --zone bedroom
   ```

3. It asks **WiFi password for MyHomeWiFi:**. Type your WiFi password and press
   Return. **Nothing appears while you type.** That's on purpose, so nobody can
   see it.

The board restarts and joins your WiFi.

**Good to know:**
- The boards only use **2.4 GHz** WiFi. If your router has separate 2.4 GHz and
  5 GHz names, use the 2.4 GHz one.
- If your Mac's address ever changes (e.g. after the router restarts), repeat
  step 7.

## Step 8: Check the board is sending data

The board can stay plugged into the Mac, or go on any USB phone charger nearby.
Paste this and press Return:

```
npx @ruvnet/ruview esp32 --seconds 10
```

- The first time, it asks **Ok to proceed? (y)**. Type `y` and press Return.
- If the Mac asks whether to **accept incoming network connections** or let
  Terminal **find devices on your local network**, click **Allow**.

After 10 seconds it prints a summary. If it shows a node with packets,
**it works!** If it says **no_packets**, check that you used the 2.4 GHz WiFi
name, then repeat step 7.

**Send a screenshot of what it printed to Claude** (press **⌘ + Shift + 4**
and drag over the Terminal window), and we'll go from there.

## Step 8½: Watch it sense, in plain English

```
python3 presence.py
```

Every 3 seconds it prints one line per board: whether someone seems to be
there, whether they're moving, and the board's **fall flag**. Walk around,
stand still, leave the room, and watch it change. Press **Control + C** to
stop. These are the board's own experimental estimates, so test them before
trusting them.

## Step 9: The other boards (later)

For each board: plug it in alone, then do steps 5–7 again with these changes.

| Board | In step 6, change `esp32c6-4mb` to | `--chip` | `--flash-size` |
|---|---|---|---|
| Waveshare ESP32-C6-LCD-1.47 | `esp32c6-4mb` (as written) | `esp32c6` | `4MB` |
| Seeed XIAO ESP32-S3 Sense | `xiao-esp32s3-8mb` | `esp32s3` | `8MB` |
| Waveshare ESP32-S3-Touch-LCD-1.83 | `xiao-esp32s3-8mb` | `esp32s3` | `8MB` |
| Waveshare ESP32-S3-Zero | `esp32s3-zero-4mb` | `esp32s3` | `4MB` |

- In step 7, give each board its own number (`--node-id 2`, `--node-id 3`, …)
  and a room name (`--zone bathroom`, `--zone kitchen`, …).
- The screens on the Waveshare boards stay blank; that's expected.
- **S3-Zero warning:** this tiny board can get hot running this firmware, and
  one user's boards broke after overheating. Don't cover it, give it some air,
  and touch it after a few minutes. If it's uncomfortably hot, unplug it.

---

# Technical details

Built from [ruvnet/RuView](https://github.com/ruvnet/RuView) `a175477`
(2026-11-09), `firmware/esp32-csi-node`, with ESP-IDF v5.4
(`espressif/idf:v5.4` Docker image). Each folder has `SHA256SUMS.txt`
(`shasum -a 256 -c SHA256SUMS.txt` to verify on a Mac).

| Folder | Boards | Flash | Settings |
|---|---|---|---|
| `esp32c6-4mb/` | Waveshare ESP32-C6-LCD-1.47 | 4 MB | `sdkconfig.defaults` + `sdkconfig.defaults.esp32c6` + `sdkconfig.defaults.devkitc` |
| `xiao-esp32s3-8mb/` | Seeed XIAO ESP32-S3 Sense, Waveshare ESP32-S3-Touch-LCD-1.83 | 8 MB | `sdkconfig.defaults` + `sdkconfig.defaults.devkitc` |
| `esp32s3-zero-4mb/` | Waveshare ESP32-S3-Zero | 4 MB | `sdkconfig.defaults` + `sdkconfig.defaults.4mb` |

- **Display support is compiled out of all three.** On a board with no screen,
  the default build can falsely detect one and then capture no CSI at all
  (RuView#893). RuView only drives an SH8601 AMOLED panel, so the Waveshare
  boards' ST7789 LCDs aren't supported either way.
- **Flash layout** (all three): bootloader `0x0`, partition table `0x8000`,
  otadata `0xf000`, app `0x20000`.
- **S3-Touch-LCD-1.83** has 16 MB flash; the 8 MB image leaves the rest unused.
- **`provision.py`** is an unmodified copy of RuView's
  `firmware/esp32-csi-node/provision.py` at `a175477` (MIT, see
  `LICENSE-RuView`). It writes WiFi and target settings to the board's NVS
  partition. With no `--password`, it prompts for one without echoing it.
- **Don't use RuView's `release_bins/` folder.** The project marks those files
  as old snapshots.
- RuView only counts firmware as working once a board has booted it and
  produced a boot log.

**Optional dashboard.** RuView's sensing server shows a live web dashboard. It
needs Rust (<https://rustup.rs>), Git, and a full RuView checkout:

```sh
git clone https://github.com/ruvnet/RuView && cd RuView
git submodule update --init --depth 1
cd v2 && cargo run --release -p wifi-densepose-sensing-server -- \
  --udp-bind 0.0.0.0 --udp-allow 192.168.1.0/24
# open http://localhost:8080
```

Step 8's check and the server both listen on UDP port 5005, so stop one before
starting the other. The server shows simulated data (labelled as simulated)
until a real board sends a frame.
