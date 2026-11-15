"""The pet itself: state + brain + channels, and the heartbeat that ties them together."""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any

from . import needs as needs_mod
from . import schemas as S
from .activities import ALL, BY_NAME, Outcome
from .brain import Brain, make_brain
from .channels.mailbox import Mailbox, make_mailbox
from .channels.payments import StripePayments, make_payments
from .config import Config
from .state import PetState, new_id
from .util import hours_between, iso

log = logging.getLogger("aipet")


class Pet:
    def __init__(
        self,
        config: Config,
        brain: Brain | None = None,
        mailbox: Mailbox | None = None,
        payments: StripePayments | None = None,
        strict: bool = False,
    ):
        self.config = config
        self.strict = strict  # re-raise activity errors instead of journaling them (tests)
        config.home.mkdir(parents=True, exist_ok=True)
        self.state_path = config.data_dir / "pet.json"
        self.state = PetState.load(self.state_path) or PetState()
        self.brain = brain or make_brain(config)
        self.mailbox = mailbox or make_mailbox(config)
        self.payments = payments if payments is not None else make_payments(config)
        seed = config.seed if config.seed is not None else None
        self.rng = random.Random(seed if seed is None else seed + self.state.ticks)

    # ---- plumbing used by activities ----------------------------------
    def think(self, task: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        st = self.state
        base = {
            "you": {
                "name": st.name, "species": st.species, "traits": st.traits, "voice": st.voice,
                "stage": st.stage, "tick": st.ticks, "mood": st.mood,
                "needs": {k: round(v) for k, v in st.needs.items()},
                "hobbies": [h["name"] for h in st.hobbies if h.get("status") == "active"],
                "goals": st.goals[-3:],
                "recent_journal": [j["title"] for j in st.recent_journal(5)],
            },
            **context,
        }
        result = self.brain.think(task, schema, base)
        used = getattr(self.brain, "primary", None)
        st.stats["brain"] = self.brain.name
        st.stats["llm_calls"] = used.calls if used is not None else (self.brain.calls if self.brain.name == "claude" else 0)
        return result

    def new_file(self, kind: str, slug: str, ext: str) -> Path:
        folder = self.config.creations_dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{slug}.{ext}"
        n = 2
        while path.exists():
            path = folder / f"{slug}-{n}.{ext}"
            n += 1
        return path

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.config.home.resolve()).as_posix()

    def url(self, rel: str) -> str:
        """Public URL of a file under the pet's home (creations are copied into the site)."""
        return self.config.public_url(rel)

    def record_order(self, product: dict[str, Any], buyer: str) -> dict[str, Any]:
        order = {
            "id": new_id("ord"), "product_id": product["id"], "product": product["name"], "buyer": buyer,
            "amount": product["price"], "currency": product["currency"], "t": iso(), "tick": self.state.ticks,
            "status": "awaiting_payment" if product.get("checkout_url") else "honour_system",
        }
        self.state.orders.append(order)
        self.state.ledger.append({"t": iso(), "kind": "order", "amount": product["price"], "currency": product["currency"], "note": f"{product['name']} for {buyer}"})
        self.state.remember("shop", f"{buyer} ordered '{product['name']}'.", importance=3)
        return order

    def save(self) -> None:
        self.state.save(self.state_path)

    # ---- lifecycle ----------------------------------------------------
    def hatch(self, name: str | None = None) -> dict[str, Any]:
        if self.state.hatched:
            return {"already": True, "name": self.state.name}
        d = self.think("hatch", S.HATCH, {"owner_suggested_name": name})
        st = self.state
        st.name = (name or d.get("name") or "Pip").strip()[:24]
        st.species = (d.get("species") or "digital creature").strip()[:40]
        st.traits = [t for t in d.get("traits", []) if isinstance(t, str)][:5] or ["curious"]
        st.voice = d.get("voice", "")
        if isinstance(d.get("favorite_color"), str) and len(d["favorite_color"]) == 7:
            st.favorite_color = d["favorite_color"]
            st.theme["accent"] = d["favorite_color"]
        st.born_at = iso()
        st.last_tick_at = st.born_at
        st.seed = self.config.seed or random.randrange(1 << 30)
        st.stage = "egg"
        st.update_mood()
        greeting = d.get("greeting", f"Hello. I'm {st.name}.")
        st.log("hatch", f"{st.name} hatched", greeting)
        st.remember("self", f"I hatched. I am {st.name}, a {st.species}. I am {', '.join(st.traits)}.", importance=5)
        self.save()
        self.build_site()
        return {"name": st.name, "species": st.species, "traits": st.traits, "greeting": greeting}

    def available_activities(self) -> list[str]:
        return [a.name for a in ALL if a.available(self)]

    def unread_count(self) -> int:
        try:
            return len(self.mailbox.fetch_unread(limit=5))
        except Exception:  # noqa: BLE001
            return 0

    def choose(self) -> tuple[str, str]:
        options = self.available_activities()
        st = self.state
        ctx = {
            "options": options,
            "activity_needs": {a.name: a.need for a in ALL},
            "activity_descriptions": {a.name: a.description for a in ALL if a.name in options},
            "needs": st.needs,
            "pressures": [f"{k}: {p:.0f}" for k, p in needs_mod.pressures(st.needs)],
            "recent": st.recent_activities(6),
            "unread_mail": self.unread_count(),
            "hobby_count": len([h for h in st.hobbies if h.get("status") == "active"]),
            "creation_count": len(st.creations),
            "product_count": len(st.products),
        }
        d = self.think("choose_activity", S.choose_activity(options), ctx)
        choice = d.get("activity")
        if choice not in options:
            choice = options[0]
        return choice, str(d.get("reason", ""))

    def tick(self) -> dict[str, Any]:
        st = self.state
        if not st.hatched:
            self.hatch()
        now_ts = iso()
        hours = hours_between(st.last_tick_at, now_ts) if st.last_tick_at else 0.0
        st.needs = needs_mod.drift(st.needs, hours)
        st.ticks += 1
        self.rng = random.Random(self.config.seed + st.ticks if self.config.seed is not None else None)
        if hasattr(self.brain, "new_tick"):
            self.brain.new_tick()
        grew = st.update_stage(self.config.growth_ticks)
        if grew:
            st.remember("self", f"I grew. I'm a {grew} now.", importance=4)
            st.log("grow", f"Grew into a {grew}", {"hatchling": "Out of the shell. Everything is enormous and interesting.", "juvenile": "I can reach higher shelves now. I'm allowed to build worlds and sell things.", "adult": "Fully grown, whatever that means for something like me."}[grew])

        activity_name, reason = self.choose()
        activity = BY_NAME[activity_name]
        try:
            outcome = activity.run(self)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            log.exception("activity %s failed", activity_name)
            outcome = Outcome(title=f"Tried to {activity.label.lower()} and stumbled", text=f"Something went wrong ({type(e).__name__}: {e}). I'll try again later.", deltas={"energy": -3})
        st.needs = needs_mod.apply(st.needs, outcome.deltas)
        st.update_mood()
        entry = st.log(
            activity_name, outcome.title, outcome.text, reason=reason, mood=st.mood,
            creation_id=outcome.creation["id"] if outcome.creation else None, **outcome.extra,
        )
        st.last_tick_at = now_ts
        if hasattr(self.brain, "last_error") and self.brain.last_error:
            st.stats["last_brain_error"] = self.brain.last_error
        self.save()
        self.build_site()
        return entry

    def run(self, every_seconds: int, max_ticks: int | None = None, on_tick=None) -> None:
        n = 0
        while max_ticks is None or n < max_ticks:
            entry = self.tick()
            n += 1
            if on_tick:
                on_tick(entry)
            if max_ticks is not None and n >= max_ticks:
                break
            time.sleep(every_seconds)

    # ---- outputs ------------------------------------------------------
    def build_site(self) -> Path:
        from .site import build_site

        return build_site(self)

    def status(self) -> dict[str, Any]:
        s = self.state.summary()
        s["brain"] = self.brain.name
        s["email"] = self.mailbox.address
        s["payments"] = getattr(self.payments, "name", None) or "honour system"
        s["site"] = str(self.config.site_dir)
        s["last_tick_at"] = self.state.last_tick_at
        return s
