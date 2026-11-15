from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import schemas as S
from ..audio.midi import MidiWriter
from ..audio.synth import SAMPLE_RATE, degree_to_midi, render_piece
from ..util import slugify
from .base import Activity, Outcome, hobby_ctx

if TYPE_CHECKING:
    from ..pet import Pet

VALID_BEATS = {"0.25", "0.5", "1", "1.5", "2", "3", "4"}
GM_PROGRAM = {"sine": 80, "triangle": 81, "square": 80, "saw": 81, "pluck": 24}


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    melody = []
    for n in d.get("melody", []):
        deg = n.get("degree")
        if deg is not None:
            try:
                deg = max(-7, min(14, int(deg)))
            except (TypeError, ValueError):
                deg = 0
        beats = str(n.get("beats", "1"))
        melody.append({"degree": deg, "beats": beats if beats in VALID_BEATS else "1"})
    if len(melody) < 8:
        melody += [{"degree": (i * 2) % 7, "beats": "1"} for i in range(8 - len(melody))]
    bass = [max(-7, min(7, int(b))) for b in (d.get("bass") or [0, 3, 4, 0])][:16] or [0]
    return {
        "title": (d.get("title") or "untitled").strip()[:60],
        "mood": d.get("mood", ""),
        "bpm": max(50, min(190, int(d.get("bpm", 100)))),
        "root": d.get("root") if d.get("root") in S.ROOTS else "C",
        "scale": d.get("scale") if d.get("scale") in S.SCALES else "major",
        "waveform": d.get("waveform") if d.get("waveform") in S.WAVEFORMS else "sine",
        "drums": d.get("drums") if d.get("drums") in S.DRUM_STYLES else "none",
        "melody": melody[:96],
        "bass": bass,
        "liner_notes": d.get("liner_notes", ""),
    }


class MusicActivity(Activity):
    name = "music"
    label = "Composing"
    need = "expression"
    description = "writes a melody and bass line, renders them to WAV and MIDI"

    def run(self, pet: "Pet", hobby: dict[str, Any] | None = None) -> Outcome:
        recent = [c["title"] for c in pet.state.creations_of("music")[-5:]]
        d = _clean(pet.think("compose", S.COMPOSE, {"recent_titles": recent, "hobby": hobby_ctx(hobby)}))
        slug = slugify(d["title"])
        wav = pet.new_file("music", slug, "wav")
        mid = pet.new_file("music", slug, "mid")
        notes = pet.new_file("music", slug, "md")

        samples, total_beats = render_piece(
            d["melody"], d["bass"], d["bpm"], d["root"], d["scale"], d["waveform"], d["drums"], path=wav, seed=pet.rng.randrange(1 << 20)
        )
        seconds = round(len(samples) / SAMPLE_RATE, 1)

        mw = MidiWriter(d["bpm"])
        mw.program(0, GM_PROGRAM[d["waveform"]])
        mw.program(1, 33)
        t = 0.0
        for n in d["melody"]:
            dur = float(n["beats"])
            if n["degree"] is not None:
                mw.note(0, degree_to_midi(n["degree"], d["root"], d["scale"]), t, dur * 0.9)
            t += dur
        bars = max(1, int(-(-total_beats // 4)))
        for bar in range(bars):
            mw.note(1, degree_to_midi(d["bass"][bar % len(d["bass"])], d["root"], d["scale"], -2), bar * 4, 3.8, 80)
            if d["drums"] != "none":
                for beat in range(4):
                    if beat in (0, 2):
                        mw.note(9, 36, bar * 4 + beat, 0.25, 100)
                    if d["drums"] in ("steady", "busy") and beat in (1, 3):
                        mw.note(9, 42, bar * 4 + beat, 0.25, 70)
        mw.write(mid)

        notes.write_text(
            f"# {d['title']}\n\n*{d['mood']}* — {d['bpm']} bpm, {d['root']} {d['scale']}, {d['waveform']} voice, drums: {d['drums']}.\n\n{d['liner_notes']}\n",
            encoding="utf-8",
        )
        creation = pet.state.add_creation(
            "music", d["title"], [pet.rel(wav), pet.rel(mid), pet.rel(notes)],
            bpm=d["bpm"], root=d["root"], scale=d["scale"], mood=d["mood"], seconds=seconds,
            notes=d["liner_notes"], hobby=hobby["name"] if hobby else None,
        )
        pet.state.remember("made", f"Composed '{d['title']}', a {d['mood']} piece in {d['root']} {d['scale']}.")
        return Outcome(
            title=f"Composed “{d['title']}”",
            text=f"{d['liner_notes']} ({d['bpm']} bpm, {d['root']} {d['scale']}, {len(d['melody'])} notes, {seconds}s)",
            deltas={"expression": 35, "energy": -12, "ambition": 4},
            creation=creation,
        )
