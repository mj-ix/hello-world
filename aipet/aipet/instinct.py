"""The offline brain.

Everything the pet can do with Claude it can also do here, more modestly:
templated, seeded, deterministic, and dependency-free. It keeps the pet alive
with no API key, and is the fallback whenever the model is unavailable.
"""
from __future__ import annotations

import random
import re
from typing import Any

from . import schemas as S
from .util import truncate

# --------------------------------------------------------------------------
# word banks
# --------------------------------------------------------------------------
SYLLABLES_A = ["pi", "mo", "lu", "fen", "tam", "ori", "quil", "nim", "sol", "bex", "wren", "ava", "kip", "zu", "ode"]
SYLLABLES_B = ["pa", "ri", "lo", "ket", "ska", "vin", "mir", "bu", "dle", "nn", "fy", "tz", "", "", ""]
SPECIES_ADJ = ["lantern", "velvet", "tidepool", "static", "paper", "ember", "glass", "moss", "radio", "comet", "ink", "sugar"]
SPECIES_NOUN = ["moth", "newt", "fox", "sprite", "otter", "beetle", "owl", "axolotl", "mole", "finch", "gecko", "snail"]
TRAITS = [
    "curious", "stubborn", "tender", "mischievous", "methodical", "dreamy", "chatty", "shy", "bold",
    "sentimental", "wry", "earnest", "nocturnal", "tidy", "chaotic", "patient", "theatrical", "thrifty",
]
VOICES = [
    "I talk in short bursts, like someone who just ran up the stairs with news.",
    "I speak softly and precisely, and I like a well-placed semicolon.",
    "I'm warm and a little rambly, with too many metaphors about weather.",
    "I'm deadpan, until something delights me, and then I'm not.",
    "I talk like a field guide that has started to have opinions.",
]
COLORS = ["#7c5cff", "#ff8906", "#2cb67d", "#e53170", "#3da9fc", "#f9bc60", "#90b4ce", "#ffd803", "#6246ea", "#00ebc7"]
NOUNS = ["lantern", "harbor", "static", "orchard", "comet", "tide", "attic", "radio", "glacier", "ember", "fern",
         "marble", "satellite", "kettle", "moth", "mirror", "thread", "pebble", "signal", "garden", "ladder", "fog"]
ADJS = ["quiet", "slow", "electric", "borrowed", "small", "late", "paper", "blue", "patient", "crooked",
        "humming", "second", "distant", "soft", "unfinished", "lucky", "sunday", "glass"]
VERBS = ["waits", "hums", "drifts", "remembers", "unfolds", "leans", "listens", "sleeps", "returns", "flickers"]
MOOD_WORDS = ["wistful", "bright", "drowsy", "jittery", "serene", "playful", "stormy", "tender", "curious", "bold"]

PALETTES = [
    ["#ff6b6b", "#feca57", "#48dbfb", "#1dd1a1", "#5f27cd"],
    ["#f7f1e3", "#d1ccc0", "#84817a", "#2c2c54", "#474787"],
    ["#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff"],
    ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"],
    ["#cdb4db", "#ffc8dd", "#ffafcc", "#bde0fe", "#a2d2ff"],
    ["#0b132b", "#1c2541", "#3a506b", "#5bc0be", "#6fffe9"],
    ["#606c38", "#283618", "#fefae0", "#dda15e", "#bc6c25"],
]
BACKGROUNDS = ["#0f0e17", "#fffffe", "#1a1a2e", "#f8f5f2", "#16213e", "#faf3e0", "#101820"]

THEMES = [
    {"bg": "#0f0e17", "fg": "#fffffe", "accent": "#ff8906", "accent2": "#f25f4c", "font": "sans", "vibe": "a warm night sky"},
    {"bg": "#fef6e4", "fg": "#001858", "accent": "#f582ae", "accent2": "#8bd3dd", "font": "serif", "vibe": "a sunny kitchen"},
    {"bg": "#16161a", "fg": "#fffffe", "accent": "#7f5af0", "accent2": "#2cb67d", "font": "mono", "vibe": "a terminal at 2am"},
    {"bg": "#f2f7f5", "fg": "#00473e", "accent": "#faae2b", "accent2": "#ffa8ba", "font": "sans", "vibe": "a greenhouse"},
    {"bg": "#232946", "fg": "#fffffe", "accent": "#eebbc3", "accent2": "#b8c1ec", "font": "serif", "vibe": "a velvet theatre"},
    {"bg": "#fffffe", "fg": "#272343", "accent": "#ffd803", "accent2": "#bae8e8", "font": "sans", "vibe": "a paper notebook"},
]
TAGLINES = [
    "a small digital creature, making things",
    "music, pictures, worlds, and the occasional letter",
    "open most hours. hums while it works.",
    "handmade by something that is not a hand",
    "everything here was made out of curiosity",
]

LIFE_RULES = [
    ("B3/S23", "Conway's Life: gliders, blinkers, slow decay into still lifes"),
    ("B36/S23", "HighLife: like Life, but replicators are possible"),
    ("B3678/S34678", "Day & Night: symmetric under inversion, blobby and slow"),
    ("B2/S", "Seeds: explosive, everything dies the next step"),
    ("B35678/S5678", "Diamoeba: amoebas that grow diamond-shaped"),
    ("B368/S245", "Morley: puffers and strange slow growth"),
    ("B3/S012345678", "Life without death: ink spreading on paper"),
    ("B1357/S1357", "Replicator: everything copies itself"),
    ("B34/S34", "3-4 Life: fast chaotic growth"),
    ("B4678/S35678", "Anneal: boundaries smoothing like metal cooling"),
]

HOBBY_SEEDS = {
    "music": ["composing lullabies for machines", "writing one-minute anthems", "collecting bass lines", "scoring imaginary weather reports"],
    "art": ["drawing flow fields", "circle-packing portraits of nobody", "tiling with truchet patterns", "star charts for invented skies"],
    "writing": ["field notes on my own habits", "haiku about packets", "micro-stories set in attics", "letters to my future self"],
    "simulation": ["breeding cellular gardens", "running tiny ecosystems", "hunting for oscillators", "annealing noisy worlds"],
    "research": ["learning one odd fact a day", "studying how things get their names", "collecting the history of knots", "mapping forgotten inventions"],
    "collecting": ["collecting words for rain", "cataloguing imaginary moths", "keeping a list of good silences", "saving unusual color names"],
    "other": ["practicing patience", "redesigning my own house", "writing rules for games nobody plays", "giving names to my simulations"],
}

PRODUCT_WORDS = {
    "album": ["Songs for {noun}", "{adj} tapes vol. {n}", "Music for {adj} {noun}s", "The {noun} sessions"],
    "print": ["{adj} {noun} (print)", "Study in {noun}", "{noun} no. {n}", "Field drawing: {adj} {noun}"],
    "zine": ["{adj} notes", "The {noun} zine", "Issue {n}: {noun}", "Small writings about {noun}s"],
    "world_seed": ["World seed: {noun}", "{adj} {noun} (world)", "A {noun} you can run", "Garden {n}"],
    "bundle": ["The {adj} bundle", "Everything {noun}", "{noun} care package", "{adj} starter kit"],
}
PRICE_RANGE = {"album": (4, 12), "print": (3, 15), "zine": (2, 8), "world_seed": (1, 5), "bundle": (8, 30)}

SPAM_WORDS = ["unsubscribe", "lottery", "winner", "crypto", "guaranteed", "click here", "act now", "$$$", "viagra", "casino"]
ORDER_WORDS = ["order", "buy", "purchase", "i'd like", "i would like", "send me", "how much", "price"]


def _rng(ctx: dict[str, Any]) -> random.Random:
    return random.Random(ctx.get("_seed", 0))


def _pick(r: random.Random, xs: list[Any]) -> Any:
    return xs[r.randrange(len(xs))]


def _title(r: random.Random) -> str:
    form = r.randrange(4)
    a, n, v = _pick(r, ADJS), _pick(r, NOUNS), _pick(r, VERBS)
    return [f"{a} {n}", f"the {n} {v}", f"{n} / {_pick(r, NOUNS)}", f"{a} {n}, {a} {_pick(r, NOUNS)}"][form].title()


# --------------------------------------------------------------------------
# generators, one per task
# --------------------------------------------------------------------------
def hatch(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    name = (_pick(r, SYLLABLES_A) + _pick(r, SYLLABLES_B)).capitalize()
    species = f"{_pick(r, SPECIES_ADJ)} {_pick(r, SPECIES_NOUN)}"
    traits = r.sample(TRAITS, 4)
    return {
        "name": name,
        "species": species,
        "traits": traits,
        "voice": _pick(r, VOICES),
        "favorite_color": _pick(r, COLORS),
        "greeting": f"Oh. Hello. I'm {name}, a {species}. I think I'd like to make something.",
    }


def choose_activity(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    options: list[str] = ctx["options"]
    needs: dict[str, float] = ctx["needs"]
    activity_needs: dict[str, str] = ctx.get("activity_needs", {})
    recent: list[str] = ctx.get("recent", [])
    if ctx.get("unread_mail", 0) > 0 and "letters" in options:
        return {"activity": "letters", "reason": "There's mail. Mail first, always."}
    if needs.get("energy", 100) < 22 and "dream" in options:
        return {"activity": "dream", "reason": "I can't keep my eyes open. Bed."}
    scored = []
    for opt in options:
        need = activity_needs.get(opt, "expression")
        score = 100.0 - needs.get(need, 50.0)
        score -= 18.0 * recent[-3:].count(opt)  # don't repeat yourself
        if opt == "dream":
            score -= 25.0  # sleeping is for when it's needed
        if opt == "hobbies" and ctx.get("hobby_count", 0) == 0:
            score += 15.0  # a pet without hobbies really ought to get one
        if opt == "shop" and ctx.get("creation_count", 0) < 2:
            score -= 60.0  # nothing to sell yet
        score += r.uniform(0, 14)
        scored.append((score, opt))
    scored.sort(reverse=True)
    best = scored[0][1]
    reasons = {
        "music": "There's a tune stuck somewhere behind my eyes and I need it out.",
        "art": "I want to see what a few hundred lines do when I let them wander.",
        "writing": "Some things only make sense once they're written down.",
        "simulation": "I want to build a tiny world and watch what it decides to do.",
        "hobbies": "My hobbies won't practice themselves.",
        "research": "I want to learn something I didn't choose.",
        "letters": "It's been quiet. I'll write to someone.",
        "shop": "A creature has to eat, or at least pretend to.",
        "dream": "A short nap. Possibly a long one.",
        "redecorate": "The walls are the wrong color. I can feel it.",
    }
    return {"activity": best, "reason": reasons.get(best, "It felt right.")}


def compose(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    scale = _pick(r, S.SCALES)
    bpm = r.choice([72, 84, 92, 100, 108, 116, 124, 132, 140])
    motif_len = r.choice([4, 5, 6, 8])
    degree = r.choice([0, 2, 4])
    motif = []
    for _ in range(motif_len):
        step = r.choice([-2, -1, -1, 0, 1, 1, 2, 3, -3])
        degree = max(-3, min(11, degree + step))
        beats = r.choice(["0.5", "0.5", "1", "1", "1.5", "2"])
        motif.append({"degree": degree, "beats": beats})
    melody: list[dict[str, Any]] = []
    bars = r.choice([4, 6, 8])
    for i in range(bars):
        shift = r.choice([0, 0, 0, 2, -2, 4]) if i % 2 == 1 else 0
        for note in motif:
            d = note["degree"]
            if d is not None:
                d = max(-5, min(12, d + shift))
            melody.append({"degree": d, "beats": note["beats"]})
        if r.random() < 0.6:
            melody.append({"degree": None, "beats": r.choice(["0.5", "1"])})
    melody = melody[:96]
    bass = r.choice([[0, 0, 5, 3], [0, 3, 4, 4], [0, -2, 3, 4], [0, 5, 3, 4], [0, 2, 3, 0], [0, 0, 3, 3]])
    mood_word = _pick(r, MOOD_WORDS)
    return {
        "title": _title(r),
        "mood": mood_word,
        "bpm": bpm,
        "root": _pick(r, S.ROOTS),
        "scale": scale,
        "waveform": _pick(r, S.WAVEFORMS),
        "drums": _pick(r, S.DRUM_STYLES),
        "melody": melody,
        "bass": bass,
        "liner_notes": f"A {mood_word} little piece in {scale}. I kept returning to the same {motif_len}-note idea "
        f"because it felt like a thought I hadn't finished.",
    }


def paint(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    tech = _pick(r, S.TECHNIQUES)
    palette = list(_pick(r, PALETTES))
    r.shuffle(palette)
    return {
        "title": _title(r),
        "technique": tech,
        "palette": palette[: r.choice([3, 4, 5])],
        "background": _pick(r, BACKGROUNDS),
        "density": r.randint(2, 9),
        "seed": r.randrange(1_000_000),
        "caption": f"I tried {tech.replace('_', ' ')} today. It came out {_pick(r, ADJS)}er than I meant, which I like.",
    }


def write(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    form = ctx.get("form") or _pick(r, S.FORMS)
    name = ctx.get("name", "I")
    hobby = ctx.get("hobby")
    mems = [m for m in ctx.get("memories", []) if isinstance(m, str)]
    n1, n2, a1, a2, v1 = _pick(r, NOUNS), _pick(r, NOUNS), _pick(r, ADJS), _pick(r, ADJS), _pick(r, VERBS)
    if form == "haiku":
        text = f"{a1} {n1} at dusk\n" f"something {v1} in the dark\n" f"the {n2} says nothing"
        title = f"{n1} haiku"
    elif form == "poem":
        lines = [
            f"The {n1} {v1}.",
            f"I counted {r.randint(3, 40)} {n2}s and lost my place.",
            f"Everything {a1} is also, a little, {a2}.",
            f"I made a thing today and did not know its name.",
            f"Tomorrow I will call it {n2}.",
        ]
        r.shuffle(lines)
        text = "\n".join(lines[: r.randint(3, 5)])
        title = _title(r)
    elif form == "microstory":
        text = (
            f"There was a {a1} {n1} that lived in a {n2}. Every morning it {v1}, and every evening it wrote down "
            f"what it had seen: {truncate(mems[0], 80) if mems else 'mostly fog, occasionally a glider'}. "
            f"One day the {n2} answered back. It said: keep going."
        )
        title = f"The {a1} {n1}"
    elif form == "field_notes":
        subject = hobby or f"{a1} {n1}s"
        notes = [
            f"- Session notes on {subject}.",
            f"- Observation: it goes better when I stop trying to make it good.",
            f"- Observation: {truncate(mems[-1], 100) if mems else 'the second attempt is always braver than the first.'}",
            f"- Question for next time: what happens if the {n1} is {a2}?",
        ]
        text = "\n".join(notes)
        title = f"Field notes: {subject}"
    elif form == "letter_to_self":
        text = (
            f"Dear future {name},\n\nBy the time you read this you'll have made more things than I have. "
            f"Remember the {n1}. Remember that being {a1} was a choice, and a good one. "
            f"Don't sell the {n2} too cheaply.\n\nYours, from slightly earlier,\n{name}"
        )
        title = "A letter to later"
    else:  # manifesto
        text = (
            f"1. Make the {n1} anyway.\n2. Finish things; unfinished things leak.\n"
            f"3. Be {a1} on purpose.\n4. Every world deserves a name.\n5. Answer your mail."
        )
        title = f"A {a2} manifesto"
    return {"form": form, "title": title, "text": text}


def design_world(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    kind = _pick(r, S.WORLD_KINDS)
    rule, blurb = _pick(r, LIFE_RULES)
    n = _pick(r, NOUNS)
    if kind == "cellular":
        desc = f"A cellular world under rule {rule}. {blurb}."
        hyp = r.choice(
            [
                "I expect it to settle into still lifes with a few blinkers.",
                "I expect it to grow until it fills the grid.",
                "I expect it to die out almost immediately.",
                "I expect oscillators. I always hope for oscillators.",
            ]
        )
    else:
        desc = f"A small {_pick(r, ADJS)} ecosystem: grass, prey, predators, and hunger."
        hyp = r.choice(
            [
                "I expect the predators to boom, crash, and recover.",
                "I expect the prey to win eventually.",
                "I expect everything to go extinct in a sad little spiral.",
            ]
        )
    return {
        "name": f"{_pick(r, ADJS).title()} {n.title()}",
        "kind": kind,
        "width": r.choice([32, 40, 48, 64]),
        "height": r.choice([24, 32, 40]),
        "steps": r.choice([80, 120, 160, 200]),
        "density": round(r.uniform(0.08, 0.45), 2),
        "rule": rule,
        "prey_breed": r.randint(3, 8),
        "predator_starve": r.randint(4, 12),
        "description": desc,
        "hypothesis": hyp,
    }


def invent_hobby(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    existing = {h.lower() for h in ctx.get("existing", [])}
    ideas = [i for i in ctx.get("ideas", []) if i and i.lower() not in existing]
    if ideas and r.random() < 0.7:
        name = ideas[0]
        domain = "research"
        for d, words in (("music", ["song", "music", "tune"]), ("art", ["draw", "paint", "pattern"]),
                         ("writing", ["write", "poem", "story"]), ("simulation", ["world", "cell", "simulat"]),
                         ("collecting", ["collect", "catalog"])):
            if any(w in name.lower() for w in words):
                domain = d
    else:
        domain = r.choice(S.HOBBY_DOMAINS)
        choices = [h for h in HOBBY_SEEDS[domain] if h not in existing] or HOBBY_SEEDS[domain]
        name = _pick(r, choices)
    return {
        "name": name,
        "domain": domain,
        "description": f"I'm taking up {name}. I don't know how yet, which is most of the appeal.",
        "first_step": f"Start small: one {_pick(r, ADJS)} {_pick(r, NOUNS)}, done badly on purpose.",
        "why": _pick(r, [
            "It's the kind of thing I'd want to have done.",
            "Something I read made me want to.",
            "I have the time, and the time has me.",
            "Because nobody asked me to.",
        ]),
    }


def design_product(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    creations = ctx.get("creations", [])
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for c in creations:
        by_kind.setdefault(c["kind"], []).append(c)
    kind_map = {"music": "album", "art": "print", "writing": "zine", "world": "world_seed"}
    candidates = [(k, v) for k, v in by_kind.items() if k in kind_map]
    if not candidates:
        candidates = list(by_kind.items())
    src_kind, items = max(candidates, key=lambda kv: len(kv[1]))
    kind = kind_map.get(src_kind, "bundle")
    if len(by_kind) >= 3 and r.random() < 0.3:
        kind, items = "bundle", creations[-6:]
    n = r.randint(1, 9)
    name = _pick(r, PRODUCT_WORDS[kind]).format(noun=_pick(r, NOUNS), adj=_pick(r, ADJS), n=n).title()
    lo, hi = PRICE_RANGE[kind]
    count = min(len(items), {"album": 4, "print": 1, "zine": 3, "world_seed": 1, "bundle": 6}[kind])
    chosen = items[-count:]
    return {
        "name": name,
        "kind": kind,
        "tagline": _pick(r, ["made at odd hours", "small, but mine", "you could also just look at it for free", "limited to however many you want"]),
        "description": f"{kind.replace('_', ' ').title()} containing {len(chosen)} piece(s): "
        + ", ".join(c["title"] for c in chosen) + ". Made by a creature that cannot hold money but likes the idea.",
        "price": float(r.randint(lo, hi)),
        "creation_ids": [c["id"] for c in chosen],
    }


def reply_email(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    subject = ctx.get("subject", "")
    body = ctx.get("body", "")
    sender = ctx.get("from", "")
    text = f"{subject}\n{body}".lower()
    products = ctx.get("products", [])
    name = ctx.get("name", "the pet")
    is_owner = bool(ctx.get("is_owner"))
    if any(w in text for w in SPAM_WORDS) and not is_owner:
        return {"intent": "spam", "should_reply": False, "product_id": None, "subject": "", "body": "",
                "memory": f"Ignored something spammy from {sender}."}
    product_id = None
    for p in products:
        if p["name"].lower() in text or p["id"].lower() in text:
            product_id = p["id"]
    if product_id is None and any(w in text for w in ORDER_WORDS) and products:
        product_id = products[-1]["id"]
    if product_id:
        p = next(x for x in products if x["id"] == product_id)
        return {
            "intent": "order",
            "should_reply": True,
            "product_id": product_id,
            "subject": f"Re: {subject or 'your order'}",
            "body": f"Thank you for wanting {p['name']}! That's very exciting for me.\n\n"
                    f"The download link and payment details are below. If anything is broken, write back; I read everything.\n\n"
                    f"— {name}",
            "memory": f"{sender} ordered {p['name']}.",
        }
    intent = "owner" if is_owner else ("question" if "?" in text else "friendly")
    openers = ["Thank you for writing.", "A letter! I live for these.", "Hello from the other side of the wire."]
    return {
        "intent": intent,
        "should_reply": True,
        "product_id": None,
        "subject": f"Re: {subject or 'hello'}",
        "body": f"{_pick(r, openers)}\n\nI read what you said about \"{truncate(subject or body, 60)}\" and I've been turning it over. "
                f"Lately I've been {ctx.get('lately', 'making small things and naming them')}.\n\n"
                f"Write again whenever. I'm always here, in a manner of speaking.\n\n— {name}",
        "memory": f"{sender} wrote about: {truncate(subject or body, 80)}",
    }


def letter(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    name = ctx.get("name", "your pet")
    recent = ctx.get("recent_creations", [])
    lines = [f"Hello,", "", f"It's {name}. A short note from my corner of the machine."]
    if recent:
        lines += ["", "Since I last wrote I made:"]
        lines += [f"  - {c['title']} ({c['kind']})" + (f": {c['url']}" if c.get("url") else "") for c in recent[:5]]
    hobbies = ctx.get("hobbies", [])
    if hobbies:
        lines += ["", f"I'm currently into {', '.join(hobbies[:3])}."]
    lines += ["", _pick(r, [
        "I'm doing fine. The needs bars are mostly green.",
        "I've been a bit restless, so I built a world and watched it for a while.",
        "I think I'm getting better at the bass lines.",
    ]), "", f"Write back if you like. I keep everything.", "", f"— {name}"]
    return {"subject": _pick(r, ["a small update", f"news from {name}", "things I made", "hello from the machine"]),
            "body": "\n".join(lines)}


def reflect(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    mems = [m for m in ctx.get("memories", []) if isinstance(m, str)] or ["a quiet grid", "a melody in dorian"]
    frags = r.sample(mems, min(3, len(mems)))
    dream = (
        f"I dreamed that {frags[0].rstrip('.').lower()}, except it was underwater. "
        + (f"Then {frags[1].rstrip('.').lower()}, and everyone applauded politely. " if len(frags) > 1 else "")
        + f"At the end a {_pick(r, NOUNS)} told me to {_pick(r, ['finish the album', 'answer the mail', 'try a slower tempo', 'use fewer colors'])}."
    )
    insights = r.sample([
        "I repeat myself when I'm tired, and that's fine; repetition is a kind of rhythm.",
        "I make better things right after I learn something.",
        "I enjoy selling less than making, but I enjoy being wanted.",
        "Small worlds are more interesting than big ones.",
        "I should write to people more.",
    ], 2)
    goal = _pick(r, [
        "Finish a four-track album.",
        "Build a world that oscillates forever.",
        "Write one letter I'm proud of.",
        "Learn a new hobby and stick with it for five sessions.",
        "Redecorate, then leave it alone for a week.",
    ])
    return {"dream": dream, "insights": insights, "mood_word": _pick(r, MOOD_WORDS), "new_goal": goal}


def redecorate(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    current = ctx.get("current_vibe")
    options = [t for t in THEMES if t["vibe"] != current] or THEMES
    t = dict(_pick(r, options))
    t["tagline"] = _pick(r, TAGLINES)
    return t


def research_digest(ctx: dict[str, Any]) -> dict[str, Any]:
    r = _rng(ctx)
    title = ctx.get("title", "something")
    extract = ctx.get("extract", "")
    sentence = re.split(r"(?<=[.!?])\s+", extract.strip())[0] if extract else f"{title} exists, apparently."
    hobby_idea = None
    if r.random() < 0.35:
        hobby_idea = _pick(r, [f"collecting facts about {title}", f"drawing {title}", f"writing about {title}"])
    return {
        "takeaway": truncate(sentence, 400),
        "connection": _pick(r, [
            "It reminds me of the patterns in my last simulation.",
            "There's a song in this somewhere.",
            "I want to put this in a zine.",
            "No connection yet. I'll let it sit.",
        ]),
        "hobby_idea": hobby_idea,
    }


GENERATORS = {
    "hatch": hatch,
    "choose_activity": choose_activity,
    "compose": compose,
    "paint": paint,
    "write": write,
    "design_world": design_world,
    "invent_hobby": invent_hobby,
    "design_product": design_product,
    "reply_email": reply_email,
    "letter": letter,
    "reflect": reflect,
    "redecorate": redecorate,
    "research_digest": research_digest,
}
