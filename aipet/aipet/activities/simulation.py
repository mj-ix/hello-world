from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..util import slugify
from ..worlds import run_world, thumbnail_svg, write_world_page
from .base import Activity, Outcome, hobby_ctx

if TYPE_CHECKING:
    from ..pet import Pet


class SimulationActivity(Activity):
    name = "simulation"
    label = "Building a world"
    need = "curiosity"
    min_stage = "hatchling"
    description = "designs a cellular automaton or tiny ecosystem, runs it, and judges the result"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        past = [{"name": c["title"], "kind": c.get("world_kind"), "rule": c.get("rule"), "verdict": c.get("verdict")} for c in pet.state.creations_of("world")[-5:]]
        d = pet.think("design_world", S.DESIGN_WORLD, {"past_worlds": past, "hobby": hobby_ctx(hobby)})
        design = {
            "name": (d.get("name") or "untitled world").strip()[:60],
            "kind": d.get("kind") if d.get("kind") in S.WORLD_KINDS else "cellular",
            "width": max(16, min(96, int(d.get("width", 40)))),
            "height": max(12, min(64, int(d.get("height", 30)))),
            "steps": max(40, min(400, int(d.get("steps", 120)))),
            "density": max(0.02, min(0.8, float(d.get("density", 0.3)))),
            "rule": str(d.get("rule") or "B3/S23"),
            "prey_breed": max(2, min(12, int(d.get("prey_breed", 5)))),
            "predator_starve": max(2, min(20, int(d.get("predator_starve", 8)))),
            "description": d.get("description", ""),
            "hypothesis": d.get("hypothesis", ""),
        }
        seed = pet.rng.randrange(1 << 20)
        result = run_world(design, seed)
        m = result["metrics"]
        slug = slugify(design["name"])
        folder = pet.config.creations_dir / "worlds" / slug
        folder.mkdir(parents=True, exist_ok=True)
        page = folder / "index.html"
        write_world_page(page, design, result, pet.state.theme, pet.state.name)
        thumb = folder / "thumb.svg"
        thumb.write_text(thumbnail_svg(design, result["frames"][-1], pet.state.theme), encoding="utf-8")
        (folder / "design.json").write_text(json.dumps({"design": design, "seed": seed, "metrics": m}, indent=2), encoding="utf-8")
        creation = pet.state.add_creation(
            "world", design["name"], [pet.rel(page), pet.rel(thumb), pet.rel(folder / "design.json")],
            world_kind=design["kind"], rule=design["rule"] if design["kind"] == "cellular" else None,
            verdict=m["verdict"], score=m["score"], hypothesis=design["hypothesis"], frames=m["frames"],
            hobby=hobby["name"] if hobby else None,
        )
        pet.state.remember("world", f"Built '{design['name']}' ({design['kind']}): {m['verdict']}.", importance=2)
        delight = {1: "Sad. Next time, gentler rules.", 2: "Pretty, but dead. I'll add more noise next time.", 3: "Fine. Unremarkable. Alive.", 4: "Oh, I like this one.", 5: "I could watch this all day. I sort of did."}[m["score"]]
        return Outcome(
            title=f"Built a world: “{design['name']}”",
            text=f"{design['description']} I expected: {design['hypothesis']} What happened: {m['verdict']}. {delight}",
            deltas={"curiosity": 30, "expression": 10, "energy": -10},
            creation=creation,
        )
