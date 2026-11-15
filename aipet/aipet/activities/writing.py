from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..util import slugify, truncate
from .base import Activity, Outcome, hobby_ctx

if TYPE_CHECKING:
    from ..pet import Pet


class WritingActivity(Activity):
    name = "writing"
    label = "Writing"
    need = "expression"
    description = "writes haiku, poems, micro-stories, field notes and letters to itself"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None, form: str | None = None) -> Outcome:
        ctx = {
            "recent_forms": [c.get("form") for c in pet.state.creations_of("writing")[-5:]],
            "memories": [m["text"] for m in pet.state.memories[-8:]],
            "hobby": hobby_ctx(hobby),
        }
        if form:
            ctx["form"] = form
        d = pet.think("write", S.WRITE, ctx)
        f = d.get("form") if d.get("form") in S.FORMS else "poem"
        title = (d.get("title") or "untitled").strip()[:80]
        text = (d.get("text") or "").strip()[:4000]
        path = pet.new_file("writing", slugify(title), "md")
        path.write_text(f"# {title}\n\n*{f.replace('_', ' ')}*\n\n{text}\n", encoding="utf-8")
        creation = pet.state.add_creation("writing", title, [pet.rel(path)], form=f, text=text, hobby=hobby["name"] if hobby else None)
        pet.state.remember("made", f"Wrote a {f.replace('_', ' ')} called '{title}'.")
        return Outcome(
            title=f"Wrote “{title}”",
            text=truncate(text, 240),
            deltas={"expression": 25, "energy": -6, "social": 4},
            creation=creation,
        )
