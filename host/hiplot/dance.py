"""`plot dance`: a minute of choreography with the pen up, for showing the plotter off.
The pen-lift relay keeps the beat. With `pen=True` the moves are drawn instead, which
makes a spirograph-like picture."""

import math
from dataclasses import replace

import numpy as np

from . import fonts, geometry, planner
from .config import Config

# Snappier than drawing: nothing is on paper, so corners can be loose.
DANCE = {"accel": 2500.0, "cornering": 0.3}

# Top speed when drawing the dance (mm/s); the dance itself goes faster.
PEN_SPEED = 120

# Pen timing floor when drawing the dance (ms): generous, since it only lifts ~20 times
# and the pen may be slower to lift than the configured timing assumes.
PEN_DOWN_MS = 300
PEN_UP_MS = 500


def routine(config: Config, start: complex, pen: bool = False) -> list[tuple[str, list[str], int]]:
    """(move name, firmware commands, duration ms), in order, around the paper's center."""
    drawing = replace(config, pen_down_ms=max(config.pen_down_ms, PEN_DOWN_MS),
                      pen_up_ms=max(config.pen_up_ms, PEN_UP_MS), settle_ms=max(config.settle_ms, 100))
    config = replace(config, **DANCE)
    center = complex(config.paper_width / 2, config.paper_height / 2)
    reach = min(config.paper_width, config.paper_height) / 2 - 15  # stay on the paper
    moves: list[tuple[str, list[str], int]] = []
    position = start

    def glide(name: str, path, speed: float, draw: bool = True):
        nonlocal position
        path = center + np.asarray(path, dtype=complex)
        if pen and draw:
            hop = planner.move_to(config, position, path[0])
            line = planner.plan([path], replace(drawing, draw_speed=min(speed, PEN_SPEED)), start=path[0])
            moves.append((name, hop.commands + line.commands, hop.duration_ms + line.duration_ms))
        else:
            plan = planner.glide(config, position, path, speed)
            moves.append((name, plan.commands, plan.duration_ms))
        position = path[-1]

    def taps(name: str, beats: list[int]):
        """Pen down and up on each beat; `beats` are ms between taps."""
        commands = []
        for beat in beats:
            commands += ["D", "W 90", "U", f"W {max(0, beat - 90)}"]
        if pen:
            commands.append(f"W {drawing.pen_up_ms}")  # fully up before moving on
        moves.append((name, commands, sum(beats) + (drawing.pen_up_ms if pen else 0)))

    def curve(f, turns: float = 1, points: int = 600):
        t = np.linspace(0, 2 * math.pi * turns, points)
        return f(t)

    glide("waking up", [0, 0], config.travel_speed, draw=False)
    glide("stretch", [0, 10, -10, 10, -10, 0, 10j, -10j, 10j, -10j, 0], 160)
    taps("four on the floor", [450] * 4)

    glide("figure eight", curve(lambda t: reach * (0.9 * np.sin(t) + 0.5j * np.sin(2 * t)), turns=2), 180)

    def spiral(t):
        return (8 + (reach - 8) * t / t[-1]) * np.exp(1j * t)
    out = curve(spiral, turns=4)
    glide("spiral out", out, 200)
    glide("spiral in", out[::-1], 200)

    glide("rose", curve(lambda t: reach * np.cos(4 * t) * np.exp(1j * t), points=900), 220)

    heart = curve(lambda t: (16 * np.sin(t) ** 3 + 1j * (13 * np.cos(t) - 5 * np.cos(2 * t)
                                                          - 2 * np.cos(3 * t) - np.cos(4 * t))) * reach / 18)
    glide("heart", heart, 150)
    glide("to the middle of it", [heart[0], 0], 150, draw=False)
    taps("heartbeat", [180, 520, 180, 520])

    width = config.paper_width / 2 - 20
    zigzag = [complex(-width + 2 * width * i / 12, reach * (1 if i % 2 else -1)) for i in range(13)]
    glide("zigzag", zigzag, 320)
    glide("big circle", curve(lambda t: reach * np.exp(1j * (t - math.pi / 2)), turns=1.5), 320)
    glide("lissajous", curve(lambda t: width * np.sin(3 * t + math.pi / 2) + 1j * reach * np.sin(2 * t),
                             points=900), 260)

    # "HI!" written one stroke at a time (in the air, unless drawing).
    letters = geometry.fit(fonts.text("HI!", size=80), (-width / 2, -reach / 2, width / 2, reach / 2), grow=False)
    for i, stroke in enumerate(geometry.optimize(letters, start=position - center)):
        glide("writing HI!" if i == 0 else "", stroke, 140)

    glide("bow", [0, 0], 120, draw=False)
    taps("thank you", [600, 900])
    return moves
