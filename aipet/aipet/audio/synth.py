"""A tiny additive synth that renders note lists to 16-bit WAV. No dependencies.

Deliberately simple: one melody voice, one bass voice, optional drums, a touch of
room (feedback delay). Fast enough in pure Python for pieces of a minute or so.
"""
from __future__ import annotations

import math
import random
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 22050

SCALE_STEPS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "pentatonic": [0, 2, 4, 7, 9],
    "blues": [0, 3, 5, 6, 7, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}
ROOT_MIDI = {"C": 60, "C#": 61, "D": 62, "D#": 63, "E": 64, "F": 65, "F#": 66, "G": 67, "G#": 68, "A": 69, "A#": 70, "B": 71}


def degree_to_midi(degree: int, root: str, scale: str, octave_shift: int = 0) -> int:
    steps = SCALE_STEPS[scale]
    n = len(steps)
    octave, idx = divmod(degree, n)
    return ROOT_MIDI[root] + 12 * (octave + octave_shift) + steps[idx]


def midi_to_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _wave_sample(form: str, phase: float) -> float:
    """phase in [0,1)."""
    if form == "sine":
        return math.sin(2 * math.pi * phase)
    if form == "square":
        return 0.6 if phase < 0.5 else -0.6
    if form == "saw":
        return 0.7 * (2 * phase - 1)
    if form == "triangle":
        return 4 * abs(phase - 0.5) - 1
    # pluck: sine with brighter harmonics that decay faster (handled in envelope)
    return math.sin(2 * math.pi * phase) * 0.7 + 0.3 * math.sin(4 * math.pi * phase)


def render_note(form: str, hz: float, seconds: float, amp: float, attack: float = 0.01, release: float = 0.08) -> array:
    n = int(seconds * SAMPLE_RATE)
    out = array("f", bytes(4 * n))
    if n <= 0:
        return out
    inc = hz / SAMPLE_RATE
    phase = 0.0
    a_n = max(1, int(attack * SAMPLE_RATE))
    r_n = max(1, int(release * SAMPLE_RATE))
    pluck = form == "pluck"
    decay = math.exp(-3.0 / max(1, n)) if pluck else 1.0
    env_level = 1.0
    for i in range(n):
        env = 1.0
        if i < a_n:
            env = i / a_n
        elif i > n - r_n:
            env = max(0.0, (n - i) / r_n)
        if pluck:
            env_level *= decay
            env *= env_level
        out[i] = amp * env * _wave_sample(form, phase)
        phase += inc
        if phase >= 1.0:
            phase -= 1.0
    return out


def _mix(dst: array, src: array, offset: int) -> None:
    end = min(len(dst), offset + len(src))
    for i in range(offset, end):
        dst[i] += src[i - offset]


def _noise_burst(seconds: float, amp: float, rng: random.Random, lowpass: float = 1.0) -> array:
    n = int(seconds * SAMPLE_RATE)
    out = array("f", bytes(4 * n))
    prev = 0.0
    for i in range(n):
        env = 1.0 - i / max(1, n)
        v = rng.uniform(-1, 1)
        prev = prev + lowpass * (v - prev)
        out[i] = amp * env * env * prev
    return out


def _kick(seconds: float, amp: float) -> array:
    n = int(seconds * SAMPLE_RATE)
    out = array("f", bytes(4 * n))
    phase = 0.0
    for i in range(n):
        t = i / max(1, n)
        hz = 120 * (1 - t) + 40
        phase += hz / SAMPLE_RATE
        out[i] = amp * (1 - t) ** 2 * math.sin(2 * math.pi * phase)
    return out


def render_piece(
    melody: list[dict],
    bass: list[int],
    bpm: int,
    root: str,
    scale: str,
    waveform: str,
    drums: str = "none",
    path: Path | None = None,
    seed: int = 0,
) -> tuple[array, float]:
    """Render the piece; returns (samples, total_beats). Writes WAV if path given."""
    beat_s = 60.0 / bpm
    total_beats = sum(float(n["beats"]) for n in melody)
    bars = max(1, math.ceil(total_beats / 4))
    total_s = bars * 4 * beat_s + 1.2
    buf = array("f", bytes(4 * int(total_s * SAMPLE_RATE)))
    rng = random.Random(seed)

    # melody
    t = 0.0
    for note in melody:
        dur = float(note["beats"])
        if note["degree"] is not None:
            hz = midi_to_hz(degree_to_midi(int(note["degree"]), root, scale))
            length = dur * beat_s * (0.9 if waveform != "pluck" else 1.0)
            _mix(buf, render_note(waveform, hz, length, 0.32), int(t * SAMPLE_RATE))
        t += dur * beat_s

    # bass: one note per bar, cycling the pattern, an octave and a bit below
    bass = bass or [0]
    for bar in range(bars):
        deg = bass[bar % len(bass)]
        hz = midi_to_hz(degree_to_midi(int(deg), root, scale, octave_shift=-2))
        start = bar * 4 * beat_s
        _mix(buf, render_note("triangle", hz, 4 * beat_s * 0.92, 0.26, attack=0.02, release=0.2), int(start * SAMPLE_RATE))

    # drums
    if drums != "none":
        for bar in range(bars):
            for beat in range(4):
                start = (bar * 4 + beat) * beat_s
                idx = int(start * SAMPLE_RATE)
                if beat in (0, 2) or (drums == "busy" and rng.random() < 0.4):
                    _mix(buf, _kick(0.18, 0.5), idx)
                if drums in ("steady", "busy") and beat in (1, 3):
                    _mix(buf, _noise_burst(0.12, 0.18, rng, lowpass=0.6), idx)
                if drums == "busy":
                    _mix(buf, _noise_burst(0.05, 0.08, rng, lowpass=0.9), idx + int(0.5 * beat_s * SAMPLE_RATE))
                elif drums == "soft" and beat == 3:
                    _mix(buf, _noise_burst(0.10, 0.08, rng, lowpass=0.4), idx)

    # a little room: feedback delay
    delay = int(0.21 * SAMPLE_RATE)
    for i in range(delay, len(buf)):
        buf[i] += 0.22 * buf[i - delay]

    # normalise + soft clip
    peak = max(1e-6, max(abs(x) for x in buf))
    gain = 0.85 / peak if peak > 0.85 else 1.0
    for i in range(len(buf)):
        buf[i] = math.tanh(buf[i] * gain * 1.1)

    if path is not None:
        write_wav(path, buf)
    return buf, total_beats


def write_wav(path: Path, samples: array) -> None:
    pcm = array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in samples))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
