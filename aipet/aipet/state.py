from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import needs as needs_mod
from .util import iso, read_json, write_json

STAGES = ("egg", "hatchling", "juvenile", "adult")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class PetState:
    name: str = ""
    species: str = ""
    traits: list[str] = field(default_factory=list)
    voice: str = ""
    favorite_color: str = "#7c5cff"
    born_at: str = ""
    last_tick_at: str = ""
    ticks: int = 0
    stage: str = "egg"
    needs: dict[str, float] = field(default_factory=needs_mod.fresh_needs)
    mood: str = "new"
    face: str = "( o )"
    seed: int = 0

    hobbies: list[dict[str, Any]] = field(default_factory=list)
    hobby_ideas: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    journal: list[dict[str, Any]] = field(default_factory=list)
    creations: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    email_log: list[dict[str, Any]] = field(default_factory=list)
    contacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    theme: dict[str, Any] = field(
        default_factory=lambda: {
            "bg": "#0f0e17",
            "fg": "#fffffe",
            "accent": "#ff8906",
            "accent2": "#f25f4c",
            "font": "sans",
            "vibe": "a warm night sky",
            "tagline": "a small digital creature, making things",
        }
    )
    stats: dict[str, Any] = field(default_factory=lambda: {"llm_calls": 0, "instinct_calls": 0, "brain": "instinct"})

    # ---- persistence -------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "PetState | None":
        data = read_json(path)
        if not data:
            return None
        st = cls()
        for k, v in data.items():
            if hasattr(st, k):
                setattr(st, k, v)
        return st

    def save(self, path: Path) -> None:
        write_json(path, asdict(self))

    # ---- helpers -----------------------------------------------------
    @property
    def hatched(self) -> bool:
        return bool(self.name)

    def remember(self, kind: str, text: str, importance: int = 1) -> None:
        self.memories.append({"t": iso(), "tick": self.ticks, "kind": kind, "text": text, "importance": importance})
        if len(self.memories) > 400:
            # keep the important ones, drop the oldest trivia
            keep = [m for m in self.memories if m.get("importance", 1) >= 3]
            rest = [m for m in self.memories if m.get("importance", 1) < 3]
            self.memories = (keep + rest[-250:])[-400:]
            self.memories.sort(key=lambda m: m["t"])

    def log(self, activity: str, title: str, text: str, **extra: Any) -> dict[str, Any]:
        entry = {"t": iso(), "tick": self.ticks, "activity": activity, "title": title, "text": text, **extra}
        self.journal.append(entry)
        return entry

    def add_creation(self, kind: str, title: str, files: list[str], **meta: Any) -> dict[str, Any]:
        c = {"id": new_id(kind[:3]), "kind": kind, "title": title, "files": files, "t": iso(), "tick": self.ticks, **meta}
        self.creations.append(c)
        return c

    def creations_of(self, kind: str) -> list[dict[str, Any]]:
        return [c for c in self.creations if c["kind"] == kind]

    def recent_journal(self, n: int = 6) -> list[dict[str, Any]]:
        return self.journal[-n:]

    def recent_activities(self, n: int = 6) -> list[str]:
        return [j["activity"] for j in self.journal[-n:]]

    def update_mood(self) -> None:
        self.mood, self.face = needs_mod.mood(self.needs)

    def update_stage(self, growth: tuple[int, int, int]) -> str | None:
        """Return the new stage name if the pet just grew."""
        before = self.stage
        if self.ticks >= growth[2]:
            self.stage = "adult"
        elif self.ticks >= growth[1]:
            self.stage = "juvenile"
        elif self.ticks >= growth[0]:
            self.stage = "hatchling"
        else:
            self.stage = "egg"
        return self.stage if self.stage != before else None

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "species": self.species,
            "stage": self.stage,
            "ticks": self.ticks,
            "mood": self.mood,
            "face": self.face,
            "needs": {k: round(v) for k, v in self.needs.items()},
            "traits": self.traits,
            "hobbies": [h["name"] for h in self.hobbies if h.get("status") != "retired"],
            "creations": len(self.creations),
            "products": len(self.products),
            "orders": len(self.orders),
            "goals": self.goals[-3:],
        }
