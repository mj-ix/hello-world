# RuView firmware for my ESP32 boards

This folder holds ready-made software ("firmware") for the little ESP32 boards.
Once a board has it, the board joins your home WiFi and sends WiFi-sensing data
to your laptop.

**Status: built, but not yet tested on a real board.**

---

# Step-by-step guide (no experience needed)

This guide assumes a **Windows** laptop. Mac notes are at the end of each step.
Go slowly. Each step only needs to be done once unless it says otherwise.

**You'll need:**
- The laptop, plugged in and connected to your home WiFi
- One ESP32 board. Start with the **Waveshare ESP32-C6** (the one with the
  1.47" screen): it's the type RuView has confirmed works.
- A **USB-C cable that carries data**. Some cables only charge; if nothing
  happens in step 5, try a different cable.
- Your home WiFi name and password

**A few words you'll see:**
- **Terminal / Command Prompt:** a window where you type commands. You type (or
  paste) a line, press **Enter**, and wait until it finishes.
- **Paste into Command Prompt:** right-click inside the window.
- **Folder path:** where a file lives, like `C:\Users\You\Downloads`.

---

## Step 1: Install three free programs

Download and install each one. Accept the default choices unless told otherwise.

1. **Python:** go to <https://www.python.org/downloads/> and click the big yellow
   **Download Python** button. Open the file you downloaded.
   **Important:** on the first screen, tick the box **"Add python.exe to PATH"**
   at the bottom, then click **Install Now**.
2. **Node.js:** go to <https://nodejs.org/>, click the button marked **LTS**,
   open the file and click **Next** through to **Finish**.
3. **Git:** go to <https://git-scm.com/download/win>, click
   **Click here to download**, open the file and click **Next** through to
   **Finish**.

*Mac: Python from python.org (no box to tick); Node.js the same; for Git, open
Terminal, type `git`, press Enter and click **Install** when asked.*

## Step 2: Open the Command Prompt

1. Press the **Windows key** (bottom left of the keyboard, the ⊞ logo).
2. Type `cmd`
3. Click **Command Prompt**. A black window opens. Keep it open for every step
   below.

*Mac: press ⌘ + Space, type `terminal`, press Enter.*

## Step 3: Install the board tools

Copy this line, paste it into the Command Prompt (right-click), and press Enter:

```
pip install "esptool>=5.0" esp-idf-nvs-partition-gen pyserial
```

Text will scroll for a minute. It's done when it says
**Successfully installed…** and you can type again.

*If it says `'pip' is not recognized`:* Python wasn't added to PATH. Run the
Python installer again, choose **Modify**, and tick **Add Python to environment
variables**. Then close the Command Prompt and open a new one.

## Step 4: Download the firmware and RuView

Paste these lines **one at a time**, pressing Enter after each and waiting for it
to finish:

```
cd %USERPROFILE%\Documents
git clone -b ccr-cbf88bb5-osmutu https://github.com/mj-ix/hello-world.git
git clone https://github.com/ruvnet/RuView.git
```

A browser window may ask you to sign in to GitHub for the first one; do that.
You now have two folders in **Documents**: `hello-world` and `RuView`.

*Mac: use `cd ~/Documents` for the first line.*

## Step 5: Plug in the board and find its "port"

1. Plug the ESP32-C6 into the laptop with the USB-C cable.
2. Paste this and press Enter:

   ```
   python -m serial.tools.list_ports
   ```

3. It prints something like `COM5`. **Write that down**: it's your board's
   port. (If several appear, unplug the board, run it again, and see which one
   disappeared. That's the board.)

*If nothing appears:* try another cable, then try holding the small **BOOT**
button on the board while plugging it in.

*Mac: it looks like `/dev/cu.usbmodem1101`. Use that wherever you see `COM5`.*

## Step 6: Put the firmware on the board ("flashing")

1. Go into the firmware folder:

   ```
   cd %USERPROFILE%\Documents\hello-world\ruview-firmware\esp32c6-4mb
   ```

2. Copy the line below, **change `COM5` to your port from step 5**, then press
   Enter. It's one long line:

   ```
   python -m esptool --chip esp32c6 --port COM5 --baud 460800 write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB 0x0 bootloader.bin 0x8000 partition-table.bin 0xf000 ota_data_initial.bin 0x20000 esp32-csi-node.bin
   ```

3. You'll see percentages climbing. It's done when it says **Hash of data
   verified** and **Hard resetting**.

*If it says it can't connect:* hold the **BOOT** button, tap **RESET** (or
unplug and replug), let go of BOOT, and run the line again.

## Step 7: Find your laptop's address on the home network

Paste this and press Enter:

```
ipconfig
```

Look under **Wireless LAN adapter Wi-Fi** for **IPv4 Address**, something like
`192.168.1.20`. **Write it down.**

*Mac: run `ipconfig getifaddr en0` instead.*

## Step 8: Give the board your WiFi details

1. Save your WiFi password in a small file. Paste this, press Enter, and
   Notepad opens (click **Yes** to create the file):

   ```
   notepad %USERPROFILE%\Documents\wifi.txt
   ```

   Type **only** your WiFi password, then **File → Save** and close Notepad.

2. Go to the RuView folder:

   ```
   cd %USERPROFILE%\Documents\RuView
   ```

3. Copy this line and change three things: `COM5` → your port,
   `MyHomeWiFi` → your WiFi name (keep the quote marks), `192.168.1.20` → the
   address from step 7. Then press Enter:

   ```
   python firmware\esp32-csi-node\provision.py --port COM5 --ssid "MyHomeWiFi" --password-file %USERPROFILE%\Documents\wifi.txt --target-ip 192.168.1.20 --node-id 1 --zone bedroom
   ```

   The board restarts and joins your WiFi.

**Good to know:**
- The boards only use **2.4 GHz** WiFi. If your router has separate 2.4 GHz and
  5 GHz names, use the 2.4 GHz one.
- If your laptop's address from step 7 ever changes (e.g. after the router
  restarts), repeat this step with the new address.

*Mac: use `--password-file ~/Documents/wifi.txt` and forward slashes
(`firmware/esp32-csi-node/provision.py`).*

## Step 9: Check the board is sending data

Leave the board plugged in (or plug it into any USB phone charger nearby).
Paste this and press Enter:

```
npx @ruvnet/ruview esp32 --seconds 10
```

- The first time, it asks **Ok to proceed? (y)**. Type `y` and press Enter.
- If Windows shows a **firewall** pop-up, tick **Private networks** and click
  **Allow access**.

After 10 seconds it prints a summary. If it shows a node with packets, **it
works!** If it says **no_packets**, check the 2.4 GHz WiFi name and the laptop
address, then repeat step 8.

**Send a photo or copy of what it printed to Claude**, and we'll go from there.

## Step 10: The other boards (later)

Do the same steps 5–9 for each board, with these changes:

| Board | Folder in step 6 | `--chip` | `--flash-size` |
|---|---|---|---|
| Waveshare ESP32-C6-LCD-1.47 | `esp32c6-4mb` | `esp32c6` | `4MB` |
| Seeed XIAO ESP32-S3 Sense | `xiao-esp32s3-8mb` | `esp32s3` | `8MB` |
| Waveshare ESP32-S3-Touch-LCD-1.83 | `xiao-esp32s3-8mb` | `esp32s3` | `8MB` |
| Waveshare ESP32-S3-Zero | `esp32s3-zero-4mb` | `esp32s3` | `4MB` |

- In step 8, give each board its own number (`--node-id 2`, `--node-id 3`, …)
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
(`sha256sum -c SHA256SUMS.txt` to verify).

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
- **Don't use RuView's `release_bins/` folder.** The project marks those files
  as old snapshots.
- RuView only counts firmware as working once a board has booted it and
  produced a boot log.

**Optional dashboard.** RuView's sensing server shows a live web dashboard. It
needs Rust (<https://rustup.rs>) and a full RuView checkout:

```sh
cd RuView && git submodule update --init --depth 1
cd v2 && cargo run --release -p wifi-densepose-sensing-server -- \
  --udp-bind 0.0.0.0 --udp-allow 192.168.1.0/24
# open http://localhost:8080
```

Step 9's check and the server both listen on UDP port 5005, so stop one before
starting the other. The server shows simulated data (labelled as simulated)
until a real board sends a frame.
