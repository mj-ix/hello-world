from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..util import truncate
from .base import Activity, Outcome, hobby_ctx

if TYPE_CHECKING:
    from ..pet import Pet

RANDOM_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/random/summary"
USER_AGENT = "aipet/0.1 (an autonomous digital pet reading for fun)"


def fetch_random_article(timeout: float = 10.0) -> dict[str, str] | None:
    req = urllib.request.Request(RANDOM_SUMMARY, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    title = data.get("title") or ""
    extract = data.get("extract") or ""
    if not title or not extract:
        return None
    return {"title": title, "extract": extract[:1500], "url": (data.get("content_urls") or {}).get("desktop", {}).get("page", "")}


class ResearchActivity(Activity):
    name = "research"
    label = "Reading"
    need = "curiosity"
    description = "reads a random encyclopedia article and keeps what it learned"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        article = fetch_random_article() if pet.config.research_enabled else None
        if article is None:
            # no network (or research off): re-read its own notes instead
            mems = [m for m in pet.state.memories if m["kind"] in ("fact", "world", "made")]
            if mems:
                m = mems[pet.rng.randrange(len(mems))]
                article = {"title": truncate(m["text"], 50), "extract": m["text"], "url": ""}
                source = "my own notebook"
            else:
                article = {"title": "silence", "extract": "Nothing came in, so I sat with it.", "url": ""}
                source = "the quiet"
        else:
            source = "Wikipedia"
        d = pet.think("research_digest", S.RESEARCH_DIGEST, {
            "title": article["title"], "extract": article["extract"], "hobby": hobby_ctx(hobby),
            "hobbies": [h["name"] for h in pet.state.hobbies if h.get("status") == "active"],
        })
        takeaway = (d.get("takeaway") or article["extract"][:300]).strip()
        pet.state.remember("fact", f"Learned about {article['title']}: {takeaway}", importance=2)
        idea = d.get("hobby_idea")
        if isinstance(idea, str) and idea.strip():
            pet.state.hobby_ideas = (pet.state.hobby_ideas + [idea.strip()[:80]])[-10:]
        facts = pet.state.stats.setdefault("facts", [])
        facts.append({"tick": pet.state.ticks, "title": article["title"], "takeaway": takeaway, "url": article.get("url", ""), "source": source})
        pet.state.stats["facts"] = facts[-200:]
        return Outcome(
            title=f"Read about {article['title']}",
            text=f"{takeaway} {d.get('connection', '')}" + (f" New hobby idea: {idea}." if idea else ""),
            deltas={"curiosity": 28, "energy": -5, "expression": 3},
            extra={"source": source, "url": article.get("url", "")},
        )
