from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..pet import Pet

STAGE_ORDER = {"egg": 0, "hatchling": 1, "juvenile": 2, "adult": 3}


@dataclass
class Outcome:
    title: str
    text: str
    deltas: dict[str, float] = field(default_factory=dict)
    creation: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Activity:
    name = "activity"
    label = "Doing something"
    need = "expression"  # the need this mostly relieves
    min_stage = "hatchling"
    description = ""

    def available(self, pet: "Pet") -> bool:
        return STAGE_ORDER[pet.state.stage] >= STAGE_ORDER[self.min_stage]

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        raise NotImplementedError


def hobby_ctx(hobby: dict[str, Any] | None) -> dict[str, Any] | None:
    if not hobby:
        return None
    return {"name": hobby["name"], "description": hobby.get("description", ""), "sessions": hobby.get("sessions", 0), "skill": hobby.get("skill", 0)}
