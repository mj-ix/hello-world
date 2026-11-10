# LD2450 / Rd-03D radar reader for RuView

Adds HLK-LD2450 and Ai-Thinker Rd-03D support to the RuView harness
(`@ruvnet/ruview`, `harness/ruview` in [ruvnet/RuView](https://github.com/ruvnet/RuView)).
Before this, the harness could only read the Seeed MR60BHA2 and HLK-LD2410.

Both radars are 24 GHz multi-target trackers. Each report holds up to 3 targets
with x/y position (mm), speed (cm/s) and a resolution value (mm).

## What's here

| File | What it is |
|---|---|
| `ruview-ld2450.patch` | The whole change against RuView `a175477` (harness 0.9.3). Apply with `git apply` from the RuView repo root. |
| `src/devices/mmwave.js` | The updated reader, for reference. |
| `test/mmwave-ld2450.test.mjs` | 8 tests, including the datasheet's worked example frame. |

The patch also updates the CLI help, the MCP tool description, the harness
README, and one existing test that counted the auto-detect probes (now 3: MR60,
LD2410, LD2450).

## Using it

```sh
git clone https://github.com/ruvnet/RuView && cd RuView
git apply /path/to/ruview-ld2450.patch
cd harness/ruview
pip install pyserial
node bin/cli.js mmwave --port /dev/ttyUSB0 --model ld2450   # or COM5 on Windows
node bin/cli.js mmwave --port /dev/ttyUSB0 --model rd03d
node bin/cli.js mmwave --port /dev/ttyUSB0                  # auto-detect
```

Output includes `presentFraction`, `distanceCmMean` (nearest target),
`targetCountMean`, `targetCountMax`, and the last 5 frames with per-target
`xMm`, `yMm`, `speedCmS`, `distanceCm` and `angleDeg` (negative = left of the
radar's centre line).

## Wiring (USB-to-serial adapter, 256000 baud)

| Radar | Adapter |
|---|---|
| 5V | 5V |
| GND | GND |
| TX | RX |
| RX | TX |

The Rd-03D's DP/DM pins (USB) and DEBUG pin are not needed.

## Frame format

```
AA FF 03 00 | target 1 (8 bytes) | target 2 | target 3 | 55 CC
target: x int16 | y int16 | speed int16 | resolution uint16   (little-endian)
```

x, y and speed use sign-magnitude: top bit **set** means positive, the low 15
bits are the value. An all-zero slot is an empty slot.

## Status and limits

- **Tested against synthetic frames only.** The datasheet example decodes to
  the documented values (x = −782 mm, y = 1713 mm, −16 cm/s, 320 mm). Nothing has
  been read from real hardware yet.
- **The Rd-03D starts in single-target mode.** This reader never sends commands
  to the radar (like the rest of the harness, it is read-only), so an Rd-03D
  will report at most one target until it is switched to multi-target mode.
- **Auto-detect can't tell the LD2450 and Rd-03D apart** because their frames
  are identical; it reports `ld2450` for both. LD2410 and LD2450 share 256000
  baud, so auto-detect reuses one probe capture for both.
- **Host-side only.** The ESP32 firmware does not parse these radars.
- In the harness test suite, `flywheel` and the artifact-chain test fail with
  or without this change (they need dev dependencies not installed here).
  The other 294 tests pass.
