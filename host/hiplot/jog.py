"""Moving the pen by hand from the keyboard, and setting the paper origin."""

import os
import select
import sys
import termios
import tty

from . import planner
from .config import DAC_MAX, Config
from .device import Plotter

HELP = """\
Jog the pen:
  arrows / WASD   move (up arrow = +Y)
  1 2 3 4 5       step 0.1 / 1 / 5 / 10 / 50 mm
  space           pen down / up
  o               set the paper origin (lower-left corner) here
  h               go to the paper origin
  c               go to the paper center
  t               trace the paper outline, pen up
  q / Esc         quit (lifts the pen)
"""

MOVES = {
    "\x1b[A": (0, 1), "\x1b[B": (0, -1), "\x1b[C": (1, 0), "\x1b[D": (-1, 0),
    "w": (0, 1), "s": (0, -1), "d": (1, 0), "a": (-1, 0),
}
STEPS = {"1": 0.1, "2": 1.0, "3": 5.0, "4": 10.0, "5": 50.0}


def run(plotter: Plotter, config: Config):
    status = plotter.status()
    x, y = status.x, status.y
    pen_down = status.pen_down
    step = 5.0
    message = ""

    print(HELP)
    stdin = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin)
    tty.setcbreak(stdin)
    try:
        while True:
            mm = config.to_mm(x, y)
            sys.stdout.write(
                f"\r\033[K x {mm[0]:7.1f} mm ({x:4d})   y {mm[1]:7.1f} mm ({y:4d})   "
                f"step {step:g} mm   pen {'DOWN' if pen_down else 'up'}   {message}"
            )
            sys.stdout.flush()
            message = ""

            key = _read_key(stdin)
            if key in MOVES:
                dx, dy = MOVES[key]
                x = _clamp(x + round(dx * step * config.counts_per_mm_x))
                y = _clamp(y + round(dy * step * config.counts_per_mm_y))
                plotter.send(f"M {x} {y} 0")
            elif key in STEPS:
                step = STEPS[key]
            elif key == " ":
                pen_down = not pen_down
                plotter.send("D" if pen_down else "U")
            elif key == "o":
                config.save(origin_x=x, origin_y=y)
                message = "origin saved to plotter.toml"
            elif key in ("h", "c", "t"):
                if pen_down:
                    plotter.send("U")
                    pen_down = False
                x, y = _go(plotter, config, x, y, key)
            elif key in ("q", "\x1b", "\x03"):
                break
    finally:
        termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        plotter.send("U")
        print()


def _go(plotter: Plotter, config: Config, x: int, y: int, key: str) -> tuple[int, int]:
    """Pen-up moves to the origin, the center, or around the paper's edge."""
    width, height = config.paper_width, config.paper_height
    targets = {
        "h": [0j],
        "c": [complex(width / 2, height / 2)],
        "t": [0j, complex(width, 0), complex(width, height), complex(0, height), 0j],
    }[key]

    position = complex(*config.to_mm(x, y))
    for target in targets:
        plotter.run(planner.move_to(config, position, target).commands)
        position = target
    plotter.wait_idle()
    return config.to_counts(position.real, position.imag)


def _read_key(stdin: int) -> str:
    # Raw reads: Python's buffered stdin would swallow the rest of an arrow key's
    # escape sequence where select() can't see it.
    key = os.read(stdin, 1)
    if key == b"\x1b" and select.select([stdin], [], [], 0.05)[0]:
        key += os.read(stdin, 2)
    return key.decode(errors="ignore")


def _clamp(value: int) -> int:
    return max(0, min(DAC_MAX, value))
