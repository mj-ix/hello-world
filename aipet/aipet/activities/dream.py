from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..util import slugify, truncate
from .base import Activity, Outcome

if TYPE_CHECKING:
    from ..pet import Pet


class DreamActivity(Activity):
    name = "dream"
    label = "Sleeping"
    need = "energy"
    description = "sleeps, dreams, consolidates memories, and sets a goal"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        mems = [m["text"] for m in pet.state.memories[-20:]]
        d = pet.think("reflect", S.REFLECT, {
            "memories": mems,
            "journal": [j["title"] for j in pet.state.recent_journal(8)],
            "goals": pet.state.goals[-3:],
        })
        dream = (d.get("dream") or "I don't remember.").strip()
        insights = [i for i in d.get("insights", []) if isinstance(i, str) and i.strip()][:4]
        goal = (d.get("new_goal") or "").strip()
        n = len(pet.state.creations_of("dream")) + 1
        title = f"Dream {n}"
        path = pet.new_file("dreams", slugify(title), "md")
        path.write_text(f"# {title}\n\n{dream}\n\n" + "".join(f"- {i}\n" for i in insights) + (f"\nGoal: {goal}\n" if goal else ""), encoding="utf-8")
        creation = pet.state.add_creation("dream", title, [pet.rel(path)], text=dream, insights=insights, goal=goal)
        for i in insights:
            pet.state.remember("insight", i, importance=3)
        if goal:
            pet.state.goals = (pet.state.goals + [goal])[-5:]
        return Outcome(
            title=f"Slept, and dreamed ({d.get('mood_word', 'oddly')})",
            text=f"{truncate(dream, 220)} Woke up thinking: {insights[0] if insights else '...'}" + (f" New goal: {goal}" if goal else ""),
            deltas={"energy": 55, "curiosity": 5},
            creation=creation,
        )
