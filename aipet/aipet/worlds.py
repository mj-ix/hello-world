"""Tiny simulations the pet designs and runs.

Two kinds: Life-like cellular automata (any B/S rule) and a grid ecosystem of
grass, prey and predators. Both record every frame so the website can replay
them, plus a few metrics so the pet can judge whether the world was any good.
"""
from __future__ import annotations

import json
import math
import random
import re
from html import escape
from pathlib import Path
from typing import Any


def parse_rule(rule: str) -> tuple[set[int], set[int]]:
    m = re.fullmatch(r"\s*B(\d*)/S(\d*)\s*", rule.upper())
    if not m:
        return {3}, {2, 3}
    return {int(c) for c in m.group(1)}, {int(c) for c in m.group(2)}


class CellularWorld:
    kind = "cellular"
    GLYPHS = ".#"

    def __init__(self, width: int, height: int, rule: str, density: float, seed: int):
        self.w, self.h = width, height
        self.born, self.survive = parse_rule(rule)
        rng = random.Random(seed)
        self.cells = [[1 if rng.random() < density else 0 for _ in range(width)] for _ in range(height)]

    def step(self) -> None:
        w, h, c = self.w, self.h, self.cells
        nxt = [[0] * w for _ in range(h)]
        for y in range(h):
            ym, yp = (y - 1) % h, (y + 1) % h
            for x in range(w):
                xm, xp = (x - 1) % w, (x + 1) % w
                n = c[ym][xm] + c[ym][x] + c[ym][xp] + c[y][xm] + c[y][xp] + c[yp][xm] + c[yp][x] + c[yp][xp]
                nxt[y][x] = 1 if (n in self.survive if c[y][x] else n in self.born) else 0
        self.cells = nxt

    def frame(self) -> str:
        return "".join("".join(self.GLYPHS[v] for v in row) for row in self.cells)

    def stats(self) -> dict[str, int]:
        return {"alive": sum(map(sum, self.cells))}


class EcosystemWorld:
    kind = "ecosystem"
    GLYPHS = ".,ox"  # bare, grass, prey, predator
    EMPTY, GRASS, PREY, PRED = 0, 1, 2, 3

    def __init__(self, width: int, height: int, density: float, prey_breed: int, predator_starve: int, seed: int):
        self.w, self.h = width, height
        self.prey_breed, self.pred_starve = prey_breed, predator_starve
        self.rng = random.Random(seed)
        self.grid = [[self.GRASS if self.rng.random() < 0.6 else self.EMPTY for _ in range(width)] for _ in range(height)]
        self.agents: dict[tuple[int, int], dict[str, int]] = {}
        for y in range(height):
            for x in range(width):
                r = self.rng.random()
                if r < density * 0.8:
                    self.agents[(x, y)] = {"t": self.PREY, "age": 0, "hunger": 0}
                elif r < density:
                    self.agents[(x, y)] = {"t": self.PRED, "age": 0, "hunger": 0}

    def _neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        return [((x + dx) % self.w, (y + dy) % self.h) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]

    def step(self) -> None:
        rng = self.rng
        # grass regrows
        for y in range(self.h):
            row = self.grid[y]
            for x in range(self.w):
                if row[x] == self.EMPTY and rng.random() < 0.08:
                    row[x] = self.GRASS
        new: dict[tuple[int, int], dict[str, int]] = {}
        for pos, a in sorted(self.agents.items(), key=lambda kv: rng.random()):
            x, y = pos
            a["age"] += 1
            a["hunger"] += 1
            nbrs = self._neighbors(x, y)
            if a["t"] == self.PREY:
                if self.grid[y][x] == self.GRASS:
                    self.grid[y][x] = self.EMPTY
                    a["hunger"] = 0
                if a["hunger"] > self.pred_starve + 4:
                    continue  # starved
                free = [p for p in nbrs if p not in new and p not in self.agents]
                dest = rng.choice(free) if free else pos
                if dest in new:
                    continue
                new[dest] = a
                if a["age"] % self.prey_breed == 0 and free:
                    spot = rng.choice(free)
                    if spot != dest and spot not in new:
                        new[spot] = {"t": self.PREY, "age": 0, "hunger": 0}
            else:
                prey_near = [p for p in nbrs if p in self.agents and self.agents[p]["t"] == self.PREY and p not in new]
                if prey_near:
                    dest = rng.choice(prey_near)
                    self.agents.pop(dest, None)
                    a["hunger"] = 0
                    new[dest] = a
                    if a["age"] % (self.prey_breed + 2) == 0:
                        free = [p for p in nbrs if p not in new and p not in self.agents]
                        if free:
                            new[rng.choice(free)] = {"t": self.PRED, "age": 0, "hunger": 0}
                else:
                    if a["hunger"] > self.pred_starve:
                        continue
                    free = [p for p in nbrs if p not in new and p not in self.agents]
                    dest = rng.choice(free) if free else pos
                    if dest not in new:
                        new[dest] = a
        self.agents = new

    def frame(self) -> str:
        chars = []
        for y in range(self.h):
            for x in range(self.w):
                a = self.agents.get((x, y))
                chars.append(self.GLYPHS[a["t"]] if a else self.GLYPHS[self.grid[y][x]])
        return "".join(chars)

    def stats(self) -> dict[str, int]:
        prey = sum(1 for a in self.agents.values() if a["t"] == self.PREY)
        return {"prey": prey, "predators": len(self.agents) - prey}


def build_world(design: dict[str, Any], seed: int):
    if design["kind"] == "cellular":
        return CellularWorld(design["width"], design["height"], design["rule"], design["density"], seed)
    return EcosystemWorld(design["width"], design["height"], design["density"], design["prey_breed"], design["predator_starve"], seed)


def run_world(design: dict[str, Any], seed: int) -> dict[str, Any]:
    world = build_world(design, seed)
    frames, series = [], []
    seen: dict[str, int] = {}
    period = None
    died_at = None
    for i in range(design["steps"]):
        f = world.frame()
        frames.append(f)
        s = world.stats()
        series.append(s)
        if f in seen and period is None:
            period = i - seen[f]
        seen.setdefault(f, i)
        if sum(s.values()) == 0 and died_at is None:
            died_at = i
        if period is not None or died_at is not None:
            # a few more frames for the replay, then stop; nothing new will happen
            if i - (died_at if died_at is not None else seen[f]) > 6:
                break
        world.step()
    metrics = analyse(series, period, died_at, design["steps"])
    return {"frames": frames, "series": series, "metrics": metrics}


def analyse(series: list[dict[str, int]], period: int | None, died_at: int | None, steps: int) -> dict[str, Any]:
    totals = [sum(s.values()) for s in series]
    mean = sum(totals) / max(1, len(totals))
    var = sum((t - mean) ** 2 for t in totals) / max(1, len(totals))
    m: dict[str, Any] = {
        "frames": len(series),
        "final_population": totals[-1] if totals else 0,
        "peak_population": max(totals) if totals else 0,
        "mean_population": round(mean, 1),
        "volatility": round(math.sqrt(var) / (mean + 1e-9), 3),
        "period": period,
        "died_at": died_at,
    }
    if died_at is not None:
        m["verdict"] = f"everything died by step {died_at}"
        m["score"] = 1
    elif period == 1:
        m["verdict"] = f"froze into a still life at step {series.index(series[-1]) if series else 0}"
        m["score"] = 2
    elif period:
        m["verdict"] = f"settled into an oscillator with period {period}"
        m["score"] = 4
    elif m["volatility"] > 0.35:
        m["verdict"] = "boom and bust, never settled"
        m["score"] = 4
    elif len(series) >= steps:
        m["verdict"] = "still changing when I stopped watching"
        m["score"] = 5
    else:
        m["verdict"] = "quietly alive"
        m["score"] = 3
    return m


def _sparkline_svg(series: list[dict[str, int]], color: str) -> str:
    keys = list(series[0].keys()) if series else []
    w, h = 600, 120
    paths = []
    palette = [color, "#2cb67d", "#f25f4c"]
    for ki, k in enumerate(keys):
        vals = [s[k] for s in series]
        mx = max(1, max(vals))
        pts = " ".join(f"{i / max(1, len(vals) - 1) * w:.1f},{h - v / mx * (h - 6) - 3:.1f}" for i, v in enumerate(vals))
        paths.append(f'<polyline points="{pts}" fill="none" stroke="{palette[ki % 3]}" stroke-width="2"/>')
    legend = " ".join(f'<text x="{8 + 110 * i}" y="14" fill="{palette[i % 3]}" font-size="12">{escape(k)}</text>' for i, k in enumerate(keys))
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="120" xmlns="http://www.w3.org/2000/svg">{legend}{"".join(paths)}</svg>'


def write_world_page(path: Path, design: dict[str, Any], result: dict[str, Any], theme: dict[str, Any], pet_name: str) -> None:
    glyph_colors = {".": "transparent", "#": theme["accent"], ",": "#2cb67d55", "o": theme["accent"], "x": theme["accent2"]}
    data = {"w": design["width"], "h": design["height"], "frames": result["frames"], "colors": glyph_colors}
    m = result["metrics"]
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(design['name'])} - a world by {escape(pet_name)}</title>
<link rel="stylesheet" href="../../style.css">
<style>canvas{{width:100%;max-width:720px;image-rendering:pixelated;background:{theme['bg']};border:1px solid {theme['fg']}22;border-radius:8px}}
.controls button{{margin-right:.5rem}}</style></head>
<body><main class="wrap">
<p><a href="../../worlds.html">&larr; all worlds</a></p>
<h1>{escape(design['name'])}</h1>
<p class="muted">{escape(design['kind'])} world{', rule ' + escape(design['rule']) if design['kind'] == 'cellular' else ''} &middot; {design['width']}&times;{design['height']} &middot; {m['frames']} frames</p>
<p>{escape(design['description'])}</p>
<p><strong>Hypothesis:</strong> {escape(design['hypothesis'])}<br><strong>What happened:</strong> {escape(m['verdict'])}.</p>
<canvas id="c" width="{design['width'] * 10}" height="{design['height'] * 10}"></canvas>
<p class="controls"><button id="play">pause</button><button id="restart">restart</button> <span id="step" class="muted"></span></p>
{_sparkline_svg(result['series'], theme['accent'])}
<script id="data" type="application/json">{json.dumps(data)}</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const cv=document.getElementById('c'),cx=cv.getContext('2d');let i=0,on=true;
function draw(){{cx.clearRect(0,0,cv.width,cv.height);const f=D.frames[i];
for(let y=0;y<D.h;y++)for(let x=0;x<D.w;x++){{const g=f[y*D.w+x];const col=D.colors[g];if(col&&col!=='transparent'){{cx.fillStyle=col;cx.fillRect(x*10,y*10,9,9);}}}}
document.getElementById('step').textContent='step '+(i+1)+' / '+D.frames.length;}}
function tick(){{if(on){{draw();i=(i+1)%D.frames.length;}}}}
setInterval(tick,120);draw();
document.getElementById('play').onclick=e=>{{on=!on;e.target.textContent=on?'pause':'play';}};
document.getElementById('restart').onclick=()=>{{i=0;draw();}};
</script>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def thumbnail_svg(design: dict[str, Any], frame: str, theme: dict[str, Any]) -> str:
    w, h = design["width"], design["height"]
    colors = {"#": theme["accent"], ",": "#2cb67d", "o": theme["accent"], "x": theme["accent2"]}
    rects = []
    for i, g in enumerate(frame):
        c = colors.get(g)
        if c:
            rects.append(f'<rect x="{i % w}" y="{i // w}" width="1" height="1" fill="{c}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges"><rect width="{w}" height="{h}" fill="{theme["bg"]}"/>{"".join(rects)}</svg>'
