"""Pictures of what the plotter will do (from a plan) or did (from a simulator log).
Pen-down lines are black, pen-up travel is light red."""

from html import escape
from pathlib import Path

from PIL import Image, ImageDraw

from .config import Config

Strokes = list[list[complex]]


def from_commands(commands: list[str], config: Config, start_counts: tuple[int, int]) -> tuple[Strokes, Strokes]:
    """Replays firmware commands. Returns (pen-down strokes, pen-up moves) in mm."""
    down: Strokes = []
    up: Strokes = []
    x, y = start_counts
    pen_down = False
    current = [complex(*config.to_mm(x, y))]
    (down if pen_down else up).append(current)

    for line in commands:
        parts = line.split()
        if parts[0] == "M":
            x, y = int(parts[1]), int(parts[2])
            current.append(complex(*config.to_mm(x, y)))
        elif parts[0] in ("D", "U") and pen_down != (parts[0] == "D"):
            pen_down = parts[0] == "D"
            current = [complex(*config.to_mm(x, y))]
            (down if pen_down else up).append(current)
    return down, up


def from_sim_log(rows: list[tuple[int, int, int, bool]], config: Config) -> tuple[Strokes, Strokes]:
    """Replays the simulator's DAC log. Returns (pen-down strokes, pen-up moves) in mm."""
    down: Strokes = []
    up: Strokes = []
    current: list[complex] = []
    pen_down = None
    for _, x, y, is_down in rows:
        point = complex(*config.to_mm(x, y))
        if is_down != pen_down:
            pen_down = is_down
            current = [current[-1]] if current else []
            (down if pen_down else up).append(current)
        current.append(point)
    return down, up


def write(path: Path, config: Config, down: Strokes, up: Strokes, title: str = ""):
    if path.suffix.lower() == ".svg":
        path.write_text(svg(config, down, up, title))
    else:
        _write_png(path, config, down, up)


def _write_png(path: Path, config: Config, down: Strokes, up: Strokes, px_per_mm: float = 4):
    pad = 10
    width, height = config.paper_width, config.paper_height
    image = Image.new("RGB", (round(width * px_per_mm) + 2 * pad, round(height * px_per_mm) + 2 * pad), "#e8e8e8")
    draw = ImageDraw.Draw(image)

    def xy(point: complex) -> tuple[float, float]:
        return (pad + point.real * px_per_mm, pad + (height - point.imag) * px_per_mm)

    draw.rectangle([xy(complex(0, height)), xy(complex(width, 0))], fill="white", outline="#999999")
    x0, y0, x1, y1 = config.printable
    draw.rectangle([xy(complex(x0, y1)), xy(complex(x1, y0))], outline="#dddddd")
    for stroke in up:
        if len(stroke) > 1:
            draw.line([xy(p) for p in stroke], fill="#f2a0a0", width=1)
    for stroke in down:
        if len(stroke) > 1:
            draw.line([xy(p) for p in stroke], fill="black", width=2, joint="curve")
        elif stroke:
            cx, cy = xy(stroke[0])
            draw.ellipse([cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5], fill="black")
    image.save(path)


def svg(config: Config, down: Strokes, up: Strokes, title: str = "") -> str:
    width, height = config.paper_width, config.paper_height

    def points(stroke: list[complex]) -> str:
        return " ".join(f"{p.real:.2f},{height - p.imag:.2f}" for p in stroke)

    x0, y0, x1, y1 = config.printable
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
        f'viewBox="0 0 {width} {height}">',
        f"<title>{escape(title)}</title>",
        f'<rect width="{width}" height="{height}" fill="white" stroke="#999" stroke-width="0.3"/>',
        f'<rect x="{x0}" y="{height - y1}" width="{x1 - x0}" height="{y1 - y0}" fill="none" '
        f'stroke="#ddd" stroke-width="0.2"/>',
    ]
    parts += [f'<polyline points="{points(s)}" fill="none" stroke="#f2a0a0" stroke-width="0.2"/>'
              for s in up if len(s) > 1]
    parts += [f'<polyline points="{points(s)}" fill="none" stroke="black" stroke-width="0.35" '
              f'stroke-linejoin="round" stroke-linecap="round"/>' for s in down if s]
    parts.append("</svg>")
    return "\n".join(parts)
