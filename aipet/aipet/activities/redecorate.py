from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from .base import Activity, Outcome

if TYPE_CHECKING:
    from ..pet import Pet

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class RedecorateActivity(Activity):
    name = "redecorate"
    label = "Redecorating"
    need = "ambition"
    min_stage = "juvenile"
    description = "redesigns the look of its own website"

    def available(self, pet: "Pet") -> bool:
        # not more often than every 6 ticks; the walls need time to settle
        last = pet.state.theme.get("changed_tick", -99)
        return super().available(pet) and pet.state.ticks - last >= 6

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        d = pet.think("redecorate", S.REDECORATE, {
            "current": {k: pet.state.theme.get(k) for k in ("bg", "fg", "accent", "accent2", "font", "vibe")},
            "current_vibe": pet.state.theme.get("vibe"),
            "favorite_color": pet.state.favorite_color,
        })
        theme = dict(pet.state.theme)
        for k in ("bg", "fg", "accent", "accent2"):
            if isinstance(d.get(k), str) and HEX.match(d[k]):
                theme[k] = d[k]
        if d.get("font") in S.FONTS:
            theme["font"] = d["font"]
        theme["vibe"] = (d.get("vibe") or theme.get("vibe", ""))[:80]
        theme["tagline"] = (d.get("tagline") or theme.get("tagline", ""))[:120]
        theme["changed_tick"] = pet.state.ticks
        pet.state.theme = theme
        pet.state.remember("home", f"Redecorated the site: {theme['vibe']}.")
        return Outcome(
            title=f"Redecorated: {theme['vibe']}",
            text=f"New colours ({theme['bg']} / {theme['accent']}), {theme['font']} type. Tagline: “{theme['tagline']}”.",
            deltas={"ambition": 22, "expression": 10, "energy": -5},
        )
