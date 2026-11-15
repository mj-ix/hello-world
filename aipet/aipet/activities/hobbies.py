from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..state import new_id
from ..util import iso
from .base import Activity, Outcome

if TYPE_CHECKING:
    from ..pet import Pet

MAX_ACTIVE = 3


def skill_for(sessions: int) -> int:
    return int(round(100 * (1 - math.exp(-sessions / 8))))


class HobbiesActivity(Activity):
    name = "hobbies"
    label = "Hobby time"
    need = "curiosity"
    min_stage = "hatchling"
    description = "invents hobbies, practises them, and gets better over time"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        active = [h for h in pet.state.hobbies if h.get("status") == "active"]
        want_new = not active or (len(active) < MAX_ACTIVE and (pet.state.hobby_ideas or pet.rng.random() < 0.25))
        if want_new:
            return self._invent(pet)
        # practise the one that has had the least attention lately
        active.sort(key=lambda h: (h.get("last_practised_tick", -1), h.get("sessions", 0)))
        return self._practise(pet, active[0])

    def _invent(self, pet: "Pet") -> Outcome:
        d = pet.think("invent_hobby", S.INVENT_HOBBY, {
            "existing": [h["name"] for h in pet.state.hobbies],
            "ideas": pet.state.hobby_ideas[-5:],
            "recent_work": pet.state.recent_activities(6),
        })
        name = (d.get("name") or "an unnamed pursuit").strip()[:60]
        domain = d.get("domain") if d.get("domain") in S.HOBBY_DOMAINS else "other"
        h = {
            "id": new_id("hob"), "name": name, "domain": domain, "description": d.get("description", ""),
            "why": d.get("why", ""), "first_step": d.get("first_step", ""), "status": "active",
            "sessions": 0, "skill": 0, "started": iso(), "started_tick": pet.state.ticks, "log": [],
        }
        pet.state.hobbies.append(h)
        pet.state.hobby_ideas = [i for i in pet.state.hobby_ideas if i.lower() != name.lower()]
        pet.state.remember("hobby", f"Took up a new hobby: {name}.", importance=3)
        return Outcome(
            title=f"New hobby: {name}",
            text=f"{h['description']} {h['why']} First step: {h['first_step']}",
            deltas={"curiosity": 30, "ambition": 10, "energy": -4},
            extra={"hobby_id": h["id"]},
        )

    def _practise(self, pet: "Pet", h: dict[str, Any]) -> Outcome:
        from . import BY_NAME  # local import: the registry imports this module

        domain = h.get("domain", "other")
        if domain in ("music", "art", "writing", "simulation"):
            inner = BY_NAME[domain].run(pet, hobby=h)
        elif domain == "research":
            inner = BY_NAME["research"].run(pet, hobby=h)
        else:  # collecting / other: keep field notes
            inner = BY_NAME["writing"].run(pet, hobby=h, form="field_notes")
        h["sessions"] = h.get("sessions", 0) + 1
        before = h.get("skill", 0)
        h["skill"] = skill_for(h["sessions"])
        h["last_practised_tick"] = pet.state.ticks
        h.setdefault("log", []).append({"tick": pet.state.ticks, "title": inner.title, "creation_id": inner.creation["id"] if inner.creation else None})
        h["log"] = h["log"][-30:]
        note = f"Session {h['sessions']} of {h['name']}: skill {before} → {h['skill']}."
        if h["skill"] >= 90 and h["sessions"] >= 10:
            h["status"] = "mastered"
            note += " I think I've got the hang of this one; time to find something new."
            pet.state.remember("hobby", f"Mastered {h['name']} after {h['sessions']} sessions.", importance=3)
        deltas = dict(inner.deltas)
        deltas["curiosity"] = deltas.get("curiosity", 0) + 12
        deltas["ambition"] = deltas.get("ambition", 0) + 6
        return Outcome(
            title=f"Practised {h['name']}: {inner.title}",
            text=f"{inner.text} {note}",
            deltas=deltas,
            creation=inner.creation,
            extra={"hobby_id": h["id"], **inner.extra},
        )
