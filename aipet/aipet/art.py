"""Generative SVG art. Six techniques, all seeded and dependency-free."""
from __future__ import annotations

import math
import random
from html import escape
from pathlib import Path

W, H = 800, 800


def _noise_field(rng: random.Random, cells: int = 12) -> list[list[float]]:
    return [[rng.uniform(0, 2 * math.pi) for _ in range(cells + 1)] for _ in range(cells + 1)]


def _angle_at(field: list[list[float]], x: float, y: float) -> float:
    cells = len(field) - 1
    fx, fy = x / W * cells, y / H * cells
    i, j = min(cells - 1, max(0, int(fx))), min(cells - 1, max(0, int(fy)))
    tx, ty = fx - i, fy - j
    a = field[j][i] * (1 - tx) + field[j][i + 1] * tx
    b = field[j + 1][i] * (1 - tx) + field[j + 1][i + 1] * tx
    return a * (1 - ty) + b * ty


def flowfield(rng: random.Random, palette: list[str], density: int) -> list[str]:
    field = _noise_field(rng, rng.randint(5, 14))
    out = []
    for _ in range(120 * density):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        pts = [f"{x:.1f},{y:.1f}"]
        for _ in range(rng.randint(20, 70)):
            a = _angle_at(field, x, y)
            x += 4 * math.cos(a)
            y += 4 * math.sin(a)
            if not (0 <= x <= W and 0 <= y <= H):
                break
            pts.append(f"{x:.1f},{y:.1f}")
        out.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{rng.choice(palette)}" '
            f'stroke-width="{rng.uniform(0.6, 2.4):.1f}" stroke-opacity="{rng.uniform(0.35, 0.9):.2f}" stroke-linecap="round"/>'
        )
    return out


def circles(rng: random.Random, palette: list[str], density: int) -> list[str]:
    placed: list[tuple[float, float, float]] = []
    out = []
    attempts = 400 * density
    for _ in range(attempts):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        r = min(min(x, W - x, y, H - y), 120.0)
        for px, py, pr in placed:
            r = min(r, math.hypot(px - x, py - y) - pr)
            if r < 3:
                break
        if r >= 3:
            placed.append((x, y, r))
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r - 1.5:.1f}" fill="{rng.choice(palette)}" '
                f'fill-opacity="{rng.uniform(0.6, 1.0):.2f}"/>'
            )
    return out


def truchet(rng: random.Random, palette: list[str], density: int) -> list[str]:
    n = 6 + density * 2
    s = W / n
    out = []
    for j in range(n):
        for i in range(n):
            x, y = i * s, j * s
            c = rng.choice(palette)
            sw = max(2.0, s * 0.18)
            if rng.random() < 0.5:
                out.append(f'<path d="M{x:.1f},{y + s / 2:.1f} A{s / 2:.1f},{s / 2:.1f} 0 0 1 {x + s / 2:.1f},{y:.1f}" fill="none" stroke="{c}" stroke-width="{sw:.1f}"/>')
                out.append(f'<path d="M{x + s:.1f},{y + s / 2:.1f} A{s / 2:.1f},{s / 2:.1f} 0 0 1 {x + s / 2:.1f},{y + s:.1f}" fill="none" stroke="{c}" stroke-width="{sw:.1f}"/>')
            else:
                out.append(f'<path d="M{x + s / 2:.1f},{y:.1f} A{s / 2:.1f},{s / 2:.1f} 0 0 1 {x + s:.1f},{y + s / 2:.1f}" fill="none" stroke="{c}" stroke-width="{sw:.1f}"/>')
                out.append(f'<path d="M{x:.1f},{y + s / 2:.1f} A{s / 2:.1f},{s / 2:.1f} 0 0 0 {x + s / 2:.1f},{y + s:.1f}" fill="none" stroke="{c}" stroke-width="{sw:.1f}"/>')
    return out


def lissajous(rng: random.Random, palette: list[str], density: int) -> list[str]:
    out = []
    for k in range(2 + density // 2):
        a, b = rng.randint(1, 7), rng.randint(1, 7)
        delta = rng.uniform(0, math.pi)
        rx, ry = rng.uniform(0.25, 0.46) * W, rng.uniform(0.25, 0.46) * H
        pts = []
        steps = 600
        for i in range(steps + 1):
            t = 2 * math.pi * i / steps
            pts.append(f"{W / 2 + rx * math.sin(a * t + delta):.1f},{H / 2 + ry * math.sin(b * t):.1f}")
        out.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{palette[k % len(palette)]}" '
            f'stroke-width="{rng.uniform(1.0, 3.5):.1f}" stroke-opacity="0.85"/>'
        )
    return out


def constellation(rng: random.Random, palette: list[str], density: int) -> list[str]:
    stars = [(rng.uniform(20, W - 20), rng.uniform(20, H - 20)) for _ in range(25 * density)]
    out = []
    for i, (x, y) in enumerate(stars):
        # connect to the nearest couple of stars
        near = sorted(stars, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)[1:3]
        for nx, ny in near:
            if math.hypot(nx - x, ny - y) < 140:
                out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{palette[0]}" stroke-opacity="0.35" stroke-width="1"/>')
    for x, y in stars:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(1, 4):.1f}" fill="{rng.choice(palette)}"/>')
    return out


def waves(rng: random.Random, palette: list[str], density: int) -> list[str]:
    out = []
    rows = 8 + density * 3
    for j in range(rows):
        y0 = H * (j + 0.5) / rows
        amp = rng.uniform(6, 40)
        freq = rng.uniform(0.004, 0.02)
        phase = rng.uniform(0, 2 * math.pi)
        pts = [f"{x},{y0 + amp * math.sin(freq * x + phase + 0.3 * math.sin(0.002 * x * j)):.1f}" for x in range(0, W + 1, 6)]
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{palette[j % len(palette)]}" stroke-width="{rng.uniform(1.5, 5):.1f}" stroke-linecap="round"/>')
    return out


TECHNIQUES = {
    "flowfield": flowfield,
    "circles": circles,
    "truchet": truchet,
    "lissajous": lissajous,
    "constellation": constellation,
    "waves": waves,
}


def render_svg(technique: str, palette: list[str], background: str, density: int, seed: int, title: str = "") -> str:
    rng = random.Random(seed)
    body = TECHNIQUES[technique](rng, palette, max(1, min(10, density)))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">\n'
        f"<title>{escape(title)}</title>\n"
        f'<rect width="{W}" height="{H}" fill="{background}"/>\n' + "\n".join(body) + "\n</svg>\n"
    )


def save_svg(path: Path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg(**kwargs), encoding="utf-8")
