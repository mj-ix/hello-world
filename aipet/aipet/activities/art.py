from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..art import save_svg
from ..util import slugify
from .base import Activity, Outcome, hobby_ctx

if TYPE_CHECKING:
    from ..pet import Pet

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ArtActivity(Activity):
    name = "art"
    label = "Drawing"
    need = "expression"
    description = "makes generative SVG art in one of six techniques"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        recent = [(c["title"], c.get("technique")) for c in pet.state.creations_of("art")[-5:]]
        d = pet.think("paint", S.PAINT, {"recent": recent, "hobby": hobby_ctx(hobby), "favorite_color": pet.state.favorite_color})
        palette = [c for c in d.get("palette", []) if isinstance(c, str) and HEX.match(c)] or [pet.state.favorite_color, "#ffffff", "#222222"]
        technique = d.get("technique") if d.get("technique") in S.TECHNIQUES else "flowfield"
        background = d.get("background") if isinstance(d.get("background"), str) and HEX.match(d["background"]) else "#0f0e17"
        title = (d.get("title") or "untitled").strip()[:60]
        density = max(1, min(10, int(d.get("density", 5))))
        seed = int(d.get("seed", 0)) % 1_000_000
        path = pet.new_file("art", slugify(title), "svg")
        save_svg(path, technique=technique, palette=palette, background=background, density=density, seed=seed, title=title)
        creation = pet.state.add_creation(
            "art", title, [pet.rel(path)], technique=technique, palette=palette, caption=d.get("caption", ""),
            hobby=hobby["name"] if hobby else None,
        )
        pet.state.remember("made", f"Drew '{title}' with the {technique} technique.")
        return Outcome(
            title=f"Drew “{title}”",
            text=f"{d.get('caption', '')} ({technique}, density {density}, {len(palette)} colours)",
            deltas={"expression": 30, "energy": -8, "curiosity": 4},
            creation=creation,
        )
