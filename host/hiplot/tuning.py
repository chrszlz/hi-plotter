"""A one-page tuning sheet for a new pen: the same shapes at several speeds, and dashes
with several pen timings, each labeled with the setting used. Pick the best-looking
values and put them in plotter.toml.
"""

import math
from dataclasses import replace

import numpy as np

from . import fonts, geometry, jobs, planner
from .config import Config
from .geometry import Paths
from .sources import Drawing

SPEEDS = [25, 50, 75, 100, 150, 200]   # draw_speed, mm/s
PEN_MS = [50, 100, 150, 250, 400]      # pen_down_ms and pen_up_ms together


def sections(config: Config) -> list[tuple[str, Paths, Config]]:
    """(name, strokes in paper mm, settings to draw them with), in drawing order.
    Laid out at full size from the printable area's top-left, shrunk for small paper."""
    designed = _design(config)
    bx0, by0, bx1, by1 = geometry.bounds([p for _, paths, _ in designed for p in paths])
    x0, y0, x1, y1 = config.printable
    factor = min(1.0, (x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0))
    shift = complex(x0, y1) - complex(bx0, by1) * factor
    return [(name, [p * factor + shift for p in paths], settings) for name, paths, settings in designed]


def _design(config: Config) -> list[tuple[str, Paths, Config]]:
    """The sheet in design mm, top-left at (0, 0)."""
    def label(text: str, at: complex, size: float = 5) -> Paths:
        return geometry.translate(fonts.text(text, size), at)

    result = [("labels", (
        label("hi-plotter tuning sheet", 0, 6)
        + label("draw_speed (mm/s): pick the fastest that still looks clean", -14j, 4)
        + label("pen_down_ms / pen_up_ms: pick the shortest with whole dashes and no drag marks", -100j, 4)
        + [p for i, speed in enumerate(SPEEDS) for p in label(str(speed), complex(16 + 40 * i, -86), 5)]
        + [p for i, ms in enumerate(PEN_MS) for p in label(str(ms), complex(0, -110 - 16 * i), 5)]
    ), config)]

    for i, speed in enumerate(SPEEDS):
        center = complex(20 + 40 * i, -40)
        star = geometry.polygon([
            center + (15 if k % 2 == 0 else 6) * np.exp(1j * (math.pi / 2 + k * math.pi / 5)) for k in range(10)
        ])
        zigzag = np.array([complex(4 + 40 * i + 4 * k, -66 - 8 * (k % 2)) for k in range(9)])
        circle = geometry.circle(complex(20 + 40 * i, -78), 4)
        result.append((f"speed {speed}", [star, zigzag, circle], replace(config, draw_speed=speed)))

    for i, ms in enumerate(PEN_MS):
        y = -112 - 16 * i
        dashes = [np.array([complex(20 + 18 * k, y), complex(30 + 18 * k, y)]) for k in range(12)]
        result.append((f"pen {ms} ms", dashes, replace(config, pen_down_ms=ms, pen_up_ms=ms)))

    return result


def job(config: Config, start: complex = 0j) -> jobs.Job:
    """One job for the whole sheet, each section planned with its own settings."""
    combined = planner.Plan()
    position = start
    all_paths: Paths = []
    for _, paths, settings in sections(config):
        paths = geometry.optimize(paths, start=position)
        part = planner.plan(paths, settings, start=position)
        combined.commands += part.commands
        combined.duration_ms += part.duration_ms
        combined.draw_mm += part.draw_mm
        combined.travel_mm += part.travel_mm
        combined.strokes += part.strokes
        position = paths[-1][-1]
        all_paths += paths

    home = planner.move_to(config, position, 0j)
    combined.commands += home.commands
    combined.duration_ms += home.duration_ms
    combined.travel_mm += home.travel_mm
    return jobs.from_plan(Drawing(all_paths, "tune", "Tuning sheet"), combined, start)
