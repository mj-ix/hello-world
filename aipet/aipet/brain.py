"""Brains: the thing that makes decisions.

`ClaudeBrain` asks Claude for structured JSON. `InstinctBrain` is the offline,
deterministic fallback. `make_brain` wires them so a tick never dies because
the network did: every Claude failure falls back to instinct for that call.
"""
from __future__ import annotations

import json
import logging
import random
from typing import Any, Protocol

from . import instinct
from .config import Config
from .prompts import SYSTEM_PROMPT

log = logging.getLogger("aipet.brain")


class BrainError(Exception):
    pass


class Brain(Protocol):
    name: str

    def think(self, task: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...


class InstinctBrain:
    name = "instinct"

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)
        self.calls = 0

    def think(self, task: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        gen = instinct.GENERATORS.get(task)
        if gen is None:
            raise BrainError(f"instinct has no generator for task {task!r}")
        self.calls += 1
        ctx = dict(context)
        ctx["_seed"] = self._rng.randrange(1 << 30)
        return gen(ctx)


class ClaudeBrain:
    name = "claude"

    def __init__(self, config: Config, client: Any = None):
        self.config = config
        self.calls = 0
        self.failures = 0
        if client is None:
            import anthropic  # imported lazily so the offline pet needs no SDK

            client = anthropic.Anthropic(api_key=config.api_key or None)
        self.client = client

    def think(self, task: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        user = (
            f"Task: {task}\n\n"
            f"Pet state and context (JSON):\n{json.dumps(context, ensure_ascii=False, indent=1, default=str)}\n\n"
            "Decide, in character, and answer with JSON matching the schema."
        )
        self.calls += 1
        response = self.client.beta.messages.create(
            model=self.config.model,
            max_tokens=8000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.config.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise BrainError(f"model declined task {task!r}: {getattr(details, 'explanation', '') or 'refusal'}")
        if response.stop_reason == "max_tokens":
            raise BrainError(f"model output truncated on task {task!r}")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), None)
        if text is None:
            raise BrainError(f"model returned no text for task {task!r}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise BrainError(f"model returned invalid JSON for task {task!r}: {e}") from e
        if not isinstance(data, dict):
            raise BrainError(f"model returned non-object JSON for task {task!r}")
        return data


class HybridBrain:
    """Claude first, instinct when Claude can't (budget, network, refusal, bad output)."""

    name = "claude+instinct"

    def __init__(self, primary: ClaudeBrain, fallback: InstinctBrain, max_calls_per_tick: int):
        self.primary = primary
        self.fallback = fallback
        self.max_calls_per_tick = max_calls_per_tick
        self.calls_this_tick = 0
        self.last_error: str | None = None

    def new_tick(self) -> None:
        self.calls_this_tick = 0
        self.last_error = None

    def think(self, task: str, schema: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if self.calls_this_tick >= self.max_calls_per_tick:
            return self.fallback.think(task, schema, context)
        self.calls_this_tick += 1
        try:
            return self.primary.think(task, schema, context)
        except Exception as e:  # noqa: BLE001 - any failure means "use instinct for this one"
            self.primary.failures += 1
            self.last_error = f"{type(e).__name__}: {e}"
            log.warning("claude brain failed on %s, using instinct: %s", task, self.last_error)
            return self.fallback.think(task, schema, context)


def make_brain(config: Config) -> Brain:
    instinct_brain = InstinctBrain(config.seed)
    mode = config.brain
    if mode == "instinct":
        return instinct_brain
    if mode == "auto":
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return instinct_brain
        if not config.api_key:
            return instinct_brain
    try:
        primary = ClaudeBrain(config)
    except Exception as e:  # noqa: BLE001
        log.warning("could not start the Claude brain (%s); running on instinct", e)
        return instinct_brain
    return HybridBrain(primary, instinct_brain, config.max_llm_calls_per_tick)
