"""Minimal Standard MIDI File (format 0) writer. No dependencies."""
from __future__ import annotations

import struct
from pathlib import Path

TICKS_PER_BEAT = 480


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


class MidiWriter:
    def __init__(self, bpm: int):
        self.bpm = bpm
        self.events: list[tuple[int, bytes]] = []  # (absolute tick, message)

    def program(self, channel: int, program: int, at_beat: float = 0.0) -> None:
        self.events.append((int(at_beat * TICKS_PER_BEAT), bytes([0xC0 | channel, program & 0x7F])))

    def note(self, channel: int, pitch: int, start_beat: float, length_beats: float, velocity: int = 96) -> None:
        pitch = max(0, min(127, pitch))
        on = int(round(start_beat * TICKS_PER_BEAT))
        off = int(round((start_beat + max(length_beats, 0.05)) * TICKS_PER_BEAT))
        self.events.append((on, bytes([0x90 | channel, pitch, max(1, min(127, velocity))])))
        self.events.append((off, bytes([0x80 | channel, pitch, 0])))

    def write(self, path: Path) -> None:
        tempo = int(60_000_000 / self.bpm)
        track = bytearray()
        track += _vlq(0) + b"\xff\x51\x03" + struct.pack(">I", tempo)[1:]
        last = 0
        # note-offs before note-ons at the same tick so repeated notes retrigger
        for tick, msg in sorted(self.events, key=lambda e: (e[0], 0 if (e[1][0] & 0xF0) == 0x80 else 1)):
            track += _vlq(tick - last) + msg
            last = tick
        track += _vlq(0) + b"\xff\x2f\x00"
        data = b"MThd" + struct.pack(">IHHH", 6, 0, 1, TICKS_PER_BEAT) + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
