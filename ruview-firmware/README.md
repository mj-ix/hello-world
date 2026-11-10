# RuView ESP32-S3 firmware for my boards

CSI-node firmware built from [ruvnet/RuView](https://github.com/ruvnet/RuView)
`a175477` (2026-11-09), `firmware/esp32-csi-node`, with ESP-IDF v5.4
(`espressif/idf:v5.4` Docker image).

| Folder | Board | Flash | Settings |
|---|---|---|---|
| `xiao-esp32s3-8mb/` | Seeed XIAO ESP32-S3 Sense, **and** Waveshare ESP32-S3-Touch-LCD-1.83 | 8 MB | `sdkconfig.defaults` + `sdkconfig.defaults.devkitc` |
| `esp32s3-zero-4mb/` | Waveshare ESP32-S3-Zero | 4 MB | `sdkconfig.defaults` + `sdkconfig.defaults.4mb` |
| `esp32c6-4mb/` | Waveshare ESP32-C6-LCD-1.47 | 4 MB | `sdkconfig.defaults` + `sdkconfig.defaults.esp32c6` + `sdkconfig.defaults.devkitc` |

Display support is compiled out of all three. That matters: on a board with no
screen, the default build can wrongly detect one and then capture no WiFi data
at all (RuView#893). RuView's display code only drives one AMOLED panel
(SH8601); the Waveshare boards' ST7789 LCDs aren't supported, so their screens
stay blank either way.

- **S3-Touch-LCD-1.83:** it has 16 MB flash; flashing the 8 MB image with
  `--flash_size 8MB` simply leaves the rest unused.
- **C6-LCD-1.47:** flash with `--chip esp32c6 --flash_size 4MB` at the same four
  offsets. ESP32-C6 is the chip RuView has confirmed capturing data on real
  hardware. Don't use the files in RuView's `release_bins/` folder;
the project marks them as old snapshots.

**Status: built, not yet tested on a real board.** RuView only counts firmware
as working once a board has booted it and produced a boot log.

## 1. Flash (once per board, over USB)

```sh
pip install esptool pyserial
cd xiao-esp32s3-8mb            # or esp32s3-zero-4mb
sha256sum -c SHA256SUMS.txt    # check the files arrived intact
python -m esptool --chip esp32s3 --port COM7 --baud 460800 \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 8MB \
  0x0     bootloader.bin \
  0x8000  partition-table.bin \
  0xf000  ota_data_initial.bin \
  0x20000 esp32-csi-node.bin
```

For the S3-Zero use `--flash_size 4MB`. Replace `COM7` with your port
(`/dev/ttyACM0` or `/dev/cu.usbmodem…` on Linux/Mac). If the board isn't
detected, hold BOOT while plugging it in.

## 2. Give it your WiFi and the laptop's address

From a RuView checkout (`git clone https://github.com/ruvnet/RuView`):

```sh
python firmware/esp32-csi-node/provision.py --port COM7 \
  --ssid "HomeWiFi" --password-file wifi.txt \
  --target-ip 192.168.1.20 --node-id 1 --zone bedroom
```

- `--target-ip` is the laptop or computer running the sensing server.
- Give each board its own `--node-id` and a `--zone` name.
- The firmware connects on 2.4 GHz WiFi.

## 3. Run the sensing server and check data is flowing

```sh
cd v2 && cargo run --release -p wifi-densepose-sensing-server -- \
  --udp-bind 0.0.0.0 --udp-allow 192.168.1.0/24
# dashboard: http://localhost:8080
npx @ruvnet/ruview esp32 --seconds 10   # summarises packets per node
```

The server shows simulated data (and labels it simulated) until a real board
sends a frame.

## Thermal warning for the S3-Zero

The firmware keeps the WiFi radio on all the time. RuView's README says
coin-sized boards like the S3-Zero can run hot, and one user's boards failed
after overheating. Leave them uncovered with some airflow, and touch-check
them during the first few minutes.
