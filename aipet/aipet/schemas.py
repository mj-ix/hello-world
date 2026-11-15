"""JSON schemas for everything the brain is asked to decide.

Both brains (Claude and the offline instinct brain) must produce output that
validates against these, so every activity can trust the shape of what it gets.
"""
from __future__ import annotations

from typing import Any

SCALES = ["major", "minor", "dorian", "pentatonic", "blues", "lydian", "mixolydian", "harmonic_minor"]
ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
WAVEFORMS = ["sine", "triangle", "square", "saw", "pluck"]
DRUM_STYLES = ["none", "soft", "steady", "busy"]
TECHNIQUES = ["flowfield", "circles", "truchet", "lissajous", "constellation", "waves"]
FORMS = ["haiku", "poem", "microstory", "field_notes", "letter_to_self", "manifesto"]
WORLD_KINDS = ["cellular", "ecosystem"]
HOBBY_DOMAINS = ["music", "art", "writing", "simulation", "research", "collecting", "other"]
PRODUCT_KINDS = ["album", "print", "zine", "world_seed", "bundle"]
EMAIL_INTENTS = ["order", "friendly", "question", "owner", "spam", "other"]
FONTS = ["serif", "sans", "mono"]


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


def _str(desc: str = "", max_len: int | None = None) -> dict[str, Any]:
    s: dict[str, Any] = {"type": "string"}
    if desc:
        s["description"] = desc
    if max_len:
        s["maxLength"] = max_len
    return s


def _int(lo: int, hi: int, desc: str = "") -> dict[str, Any]:
    s: dict[str, Any] = {"type": "integer", "minimum": lo, "maximum": hi}
    if desc:
        s["description"] = desc
    return s


def _num(lo: float, hi: float, desc: str = "") -> dict[str, Any]:
    s: dict[str, Any] = {"type": "number", "minimum": lo, "maximum": hi}
    if desc:
        s["description"] = desc
    return s


def _enum(values: list[str], desc: str = "") -> dict[str, Any]:
    s: dict[str, Any] = {"type": "string", "enum": values}
    if desc:
        s["description"] = desc
    return s


def _arr(items: dict[str, Any], lo: int = 0, hi: int | None = None, desc: str = "") -> dict[str, Any]:
    s: dict[str, Any] = {"type": "array", "items": items, "minItems": lo}
    if hi is not None:
        s["maxItems"] = hi
    if desc:
        s["description"] = desc
    return s


HEX = {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"}

HATCH = _obj(
    {
        "name": _str("A short, pronounceable name for yourself", 24),
        "species": _str("An invented species, two or three words, e.g. 'lantern moth'", 40),
        "traits": _arr(_str(max_len=24), 3, 5, "Three to five personality traits"),
        "voice": _str("One sentence describing how you talk", 200),
        "favorite_color": HEX,
        "greeting": _str("Your first words to the world, one or two sentences", 300),
    }
)


def choose_activity(options: list[str]) -> dict[str, Any]:
    return _obj(
        {
            "activity": _enum(options, "Which activity to do right now"),
            "reason": _str("One sentence, in your own voice, about why", 200),
        }
    )


COMPOSE = _obj(
    {
        "title": _str(max_len=60),
        "mood": _str("One or two words", 30),
        "bpm": _int(50, 190),
        "root": _enum(ROOTS),
        "scale": _enum(SCALES),
        "waveform": _enum(WAVEFORMS),
        "drums": _enum(DRUM_STYLES),
        "melody": _arr(
            _obj(
                {
                    "degree": {"type": ["integer", "null"], "minimum": -7, "maximum": 14, "description": "Scale degree; 0 is the root, 7 the octave; null is a rest"},
                    "beats": _enum(["0.25", "0.5", "1", "1.5", "2", "3", "4"], "Duration in beats"),
                }
            ),
            8,
            96,
            "The melody, note by note",
        ),
        "bass": _arr(_int(-7, 7), 2, 16, "One bass scale degree per bar, loops under the melody"),
        "liner_notes": _str("A few sentences about the piece", 500),
    }
)

PAINT = _obj(
    {
        "title": _str(max_len=60),
        "technique": _enum(TECHNIQUES),
        "palette": _arr(HEX, 3, 6),
        "background": HEX,
        "density": _int(1, 10, "1 sparse, 10 dense"),
        "seed": _int(0, 999999),
        "caption": _str("One or two sentences", 300),
    }
)

WRITE = _obj(
    {
        "form": _enum(FORMS),
        "title": _str(max_len=80),
        "text": _str("The piece itself. Use newlines for line breaks.", 4000),
    }
)

DESIGN_WORLD = _obj(
    {
        "name": _str("A name for this world", 60),
        "kind": _enum(WORLD_KINDS),
        "width": _int(16, 96),
        "height": _int(12, 64),
        "steps": _int(40, 400),
        "density": _num(0.02, 0.8, "Initial fraction of live cells / creatures"),
        "rule": _str("Life-like rule in B/S notation, e.g. B3/S23 (cellular worlds only)", 20),
        "prey_breed": _int(2, 12, "Steps a prey needs to breed (ecosystem only)"),
        "predator_starve": _int(2, 20, "Steps a predator survives without eating (ecosystem only)"),
        "description": _str("What this world is, in your words", 400),
        "hypothesis": _str("What you expect to happen", 300),
    }
)

INVENT_HOBBY = _obj(
    {
        "name": _str(max_len=60),
        "domain": _enum(HOBBY_DOMAINS),
        "description": _str("What the hobby is and what you'll make or collect", 400),
        "first_step": _str("What you'll do in your first session", 200),
        "why": _str("Why this calls to you", 300),
    }
)

DESIGN_PRODUCT = _obj(
    {
        "name": _str(max_len=60),
        "kind": _enum(PRODUCT_KINDS),
        "tagline": _str(max_len=120),
        "description": _str(max_len=600),
        "price": _num(1, 200, "Price in whole currency units"),
        "creation_ids": _arr(_str(), 1, 12, "IDs of your creations included in this product"),
    }
)

REPLY_EMAIL = _obj(
    {
        "intent": _enum(EMAIL_INTENTS),
        "should_reply": {"type": "boolean"},
        "product_id": {"type": ["string", "null"], "description": "If this is an order, which product id"},
        "subject": _str(max_len=120),
        "body": _str("Plain text reply, in your voice", 3000),
        "memory": _str("One line to remember about this person", 200),
    }
)

LETTER = _obj({"subject": _str(max_len=120), "body": _str("Plain text, in your voice", 3000)})

REFLECT = _obj(
    {
        "dream": _str("A short dream, two to five sentences, surreal but rooted in recent memories", 900),
        "insights": _arr(_str(max_len=200), 1, 4, "Things you learned about yourself lately"),
        "mood_word": _str(max_len=30),
        "new_goal": _str("One concrete goal for the coming days", 200),
    }
)

REDECORATE = _obj(
    {
        "bg": HEX,
        "fg": HEX,
        "accent": HEX,
        "accent2": HEX,
        "font": _enum(FONTS),
        "vibe": _str("The feeling of the new look, a few words", 80),
        "tagline": _str("A new tagline for your site", 120),
    }
)

RESEARCH_DIGEST = _obj(
    {
        "takeaway": _str("What you learned, in your own words", 500),
        "connection": _str("How it connects to your hobbies or recent work", 300),
        "hobby_idea": {"type": ["string", "null"], "description": "A new hobby this sparks, or null"},
    }
)
