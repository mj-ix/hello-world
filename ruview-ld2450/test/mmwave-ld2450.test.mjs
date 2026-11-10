// SPDX-License-Identifier: MIT
// HLK-LD2450 / Ai-Thinker Rd-03D multi-target report parsing.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Ld2450Parser, ld2450Signed, parseMmwave, readMmwave } from '../src/devices/mmwave.js';

const HEAD = [0xaa, 0xff, 0x03, 0x00];
const TAIL = [0x55, 0xcc];
// Encode the LD2450's sign-magnitude int16 (top bit set = positive).
const enc = (v) => { const raw = v >= 0 ? 0x8000 | v : -v; return [raw & 0xff, raw >> 8]; };
const slot = (x, y, speed, res = 360) => [...enc(x), ...enc(y), ...enc(speed), res & 0xff, res >> 8];
const EMPTY = Array(8).fill(0);
const frame = (...slots) => [...HEAD, ...[...slots, EMPTY, EMPTY, EMPTY].slice(0, 3).flat(), ...TAIL];

// The datasheet's worked example: target 1 at x=-782 mm, y=1713 mm, -16 cm/s, 320 mm.
const DATASHEET = [0xaa, 0xff, 0x03, 0x00, 0x0e, 0x03, 0xb1, 0x86, 0x10, 0x00, 0x40, 0x01,
  ...EMPTY, ...EMPTY, 0x55, 0xcc];

const pumpDeps = (bytes) => ({
  python: () => '/usr/bin/python3',
  exec: async () => ({ ok: true, stdout: `HEX ${Buffer.from(bytes).toString('hex')}\nEND ${bytes.length}\n` }),
});

test('sign-magnitude decoding: top bit set is positive', () => {
  assert.equal(ld2450Signed(0x0e, 0x03), -782);
  assert.equal(ld2450Signed(0xb1, 0x86), 1713);
  assert.equal(ld2450Signed(0x00, 0x80), 0);
  assert.equal(ld2450Signed(0xff, 0xff), 32767);
});

test('decodes the datasheet example frame', () => {
  const p = new Ld2450Parser();
  const [f, ...rest] = p.feed(Buffer.from(DATASHEET));
  assert.equal(rest.length, 0);
  assert.equal(p.errors, 0);
  assert.equal(f.targetCount, 1);
  assert.equal(f.present, true);
  const t = f.targets[0];
  assert.deepEqual([t.slot, t.xMm, t.yMm, t.speedCmS, t.resolutionMm], [0, -782, 1713, -16, 320]);
  assert.equal(t.distanceCm, 188.3); // hypot(782, 1713) mm
  assert.ok(t.angleDeg < 0, 'negative x is to the left of boresight');
  assert.equal(f.distanceCm, 188.3);
});

test('three targets, nearest distance, empty slots skipped', () => {
  const p = new Ld2450Parser();
  const frames = p.feed(Buffer.from([
    ...frame(slot(500, 2000, 10), slot(-300, 800, 0), slot(0, 3000, -25)),
    ...frame(),
  ]));
  assert.equal(frames.length, 2);
  assert.equal(frames[0].targetCount, 3);
  assert.deepEqual(frames[0].targets.map((t) => t.slot), [0, 1, 2]);
  assert.equal(frames[0].distanceCm, 85.4); // the (-300, 800) target
  assert.deepEqual([frames[1].present, frames[1].targetCount, frames[1].distanceCm], [false, 0, 0]);
});

test('resynchronises after garbage, split reads and a bad tail', () => {
  const p = new Ld2450Parser();
  const good = frame(slot(100, 1000, 0));
  const bad = [...good.slice(0, -2), 0x55, 0x00];
  const stream = [0x00, 0xaa, 0xaa, 0xff, 0x13, ...bad, 0x12, ...good, ...good];
  const out = [];
  for (let i = 0; i < stream.length; i += 7) out.push(...p.feed(Buffer.from(stream.slice(i, i + 7))));
  assert.equal(out.length, 2);
  assert.equal(p.errors, 1);
  assert.equal(out[0].targets[0].yMm, 1000);
});

test('LD2410 frames are not mistaken for LD2450 frames and vice versa', () => {
  const ld2410 = [0xf4, 0xf3, 0xf2, 0xf1, 0x0d, 0x00, 0x02, 0xaa, 0x01, 0x78, 0x00, 60, 0x50, 0x00, 40, 0x2c, 0x01, 0x55, 0x00, 0xf8, 0xf7, 0xf6, 0xf5];
  assert.equal(parseMmwave('ld2450', Buffer.from(ld2410)).frames.length, 0);
  assert.equal(parseMmwave('ld2410', Buffer.from(DATASHEET)).frames.length, 0);
});

test('rd03d uses the LD2450 frame', () => {
  const { frames } = parseMmwave('rd03d', Buffer.from(DATASHEET));
  assert.equal(frames[0].targets[0].xMm, -782);
});

test('readMmwave summarises an LD2450 capture with target counts', async () => {
  const bytes = [...frame(slot(0, 1500, 0)), ...frame(slot(0, 1500, 0), slot(400, 900, 5)), ...frame()];
  const r = await readMmwave({ port: '/dev/ttyUSB0', model: 'ld2450', seconds: 1 }, pumpDeps(bytes));
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.deepEqual([r.model, r.band, r.frames, r.checksumErrors], ['ld2450', '24 GHz', 3, 0]);
  assert.equal(r.presentFraction, 0.667);
  assert.equal(r.targetCountMax, 2);
  assert.equal(r.targetCountMean, 1);
  assert.equal(r.distanceCmMean, 124.25); // mean of 150 and 98.5; the empty frame is excluded
});

test('auto detection finds an LD2450 using one shared 256000-baud probe', async () => {
  const bauds = [];
  const bytes = [...frame(slot(0, 1200, 0)), ...frame(slot(0, 1210, 0)), ...frame(slot(0, 1220, 0))];
  const deps = pumpDeps(bytes);
  const exec = deps.exec;
  deps.exec = async (cmd, args, opts) => { bauds.push(args.find((a) => /^\d{5,}$/.test(a))); return exec(cmd, args, opts); };
  const r = await readMmwave({ port: '/dev/ttyUSB0', model: 'auto', seconds: 2 }, deps);
  assert.equal(r.ok, true, JSON.stringify(r));
  assert.equal(r.detected, 'ld2450');
  // 115200 for the MR60 probe, then a single 256000 capture shared by LD2410 and LD2450.
  assert.equal(bauds.filter((b) => b === '256000').length, 1, JSON.stringify(bauds));
});
