"""The pet's drive system.

Five needs, each 0..100. High values mean the need is *satisfied*:
  energy      - restored by sleeping, spent by everything else
  curiosity   - satisfied by research, new hobbies, new worlds
  expression  - satisfied by making music, art, writing
  social      - satisfied by reading and writing letters
  ambition    - satisfied by shop work, redecorating, finishing things
Needs drift down over time at different speeds; the pet picks activities
that relieve whichever need is most pressing.
"""
from __future__ import annotations

from .util import clamp

NEEDS = ("energy", "curiosity", "expression", "social", "ambition")

# points lost per hour of wall-clock time
DRIFT_PER_HOUR = {
    "energy": 1.5,
    "curiosity": 2.5,
    "expression": 3.0,
    "social": 2.0,
    "ambition": 1.2,
}

MOODS = [
    # (min average, mood word, face)
    (80, "radiant", "(^‿^)"),
    (65, "content", "(・‿・)"),
    (50, "pensive", "(・_・)"),
    (35, "restless", "(>_<)"),
    (0, "wilted", "(x_x)"),
]


def fresh_needs() -> dict[str, float]:
    return {"energy": 90.0, "curiosity": 55.0, "expression": 50.0, "social": 60.0, "ambition": 45.0}


def drift(needs: dict[str, float], hours: float) -> dict[str, float]:
    hours = clamp(hours, 0.0, 72.0)  # a long absence doesn't zero everything
    out = {}
    for k in NEEDS:
        out[k] = clamp(needs.get(k, 50.0) - DRIFT_PER_HOUR[k] * hours, 0.0, 100.0)
    return out


def apply(needs: dict[str, float], deltas: dict[str, float]) -> dict[str, float]:
    out = dict(needs)
    for k, dv in deltas.items():
        if k in out:
            out[k] = clamp(out[k] + dv, 0.0, 100.0)
    return out


def pressures(needs: dict[str, float]) -> list[tuple[str, float]]:
    """Needs sorted from most to least pressing (pressure = 100 - satisfaction)."""
    return sorted(((k, 100.0 - needs[k]) for k in NEEDS), key=lambda kv: -kv[1])


def mood(needs: dict[str, float]) -> tuple[str, str]:
    avg = sum(needs[k] for k in NEEDS) / len(NEEDS)
    if needs["energy"] < 20:
        return "sleepy", "(-_-) zzz"
    for threshold, word, face in MOODS:
        if avg >= threshold:
            return word, face
    return "wilted", "(x_x)"


def describe(needs: dict[str, float]) -> str:
    return ", ".join(f"{k} {needs[k]:.0f}" for k in NEEDS)
