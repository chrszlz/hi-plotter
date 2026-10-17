"""`plot setup`: one guided pass through what needs paper and a pen in the plotter:
setting the scale from the bed's rulers, then picking speed and pen timing from the
tuning sheet."""

from collections.abc import Callable

from . import calibration, jobs, tuning
from .config import Config
from .device import Plotter

INTRO = """\
Setup needs a pen in the holder and a letter sheet, landscape, with its lower-left
corner under the pen after `plot park`. It takes about 6 minutes:
  1. set the scale from the plotter's rulers
  2. draw the tuning sheet and pick the best speed and pen timing
For yes/no questions Enter means yes; for values it keeps the current one."""


def run(config: Config, connect: Callable[[], Plotter],
        ask: Callable[[str], str] = input, say: Callable[[str], None] = print):
    say(INTRO)
    ask("\nPaper and pen in? Press Enter to start (Ctrl-C to stop) ")
    plotter = connect()

    if _yes(ask("\nSet the scale from the rulers? [Y/n] ")):
        calibration.with_rulers(plotter, config, ask, say)

    if _yes(ask("\nDraw the tuning sheet (about 4 minutes)? [Y/n] ")):
        job = tuning.job(config, jobs.position_mm(plotter, config))
        say(job.summary)
        jobs.stream(plotter, job)
        speed = _choose(ask, "Fastest speed that still looks clean", tuning.SPEEDS, config.draw_speed)
        pen = _choose(ask, "Shortest pen timing with whole dashes and no drag marks", tuning.PEN_MS,
                      config.pen_up_ms)
        config.save(draw_speed=float(speed), pen_down_ms=int(pen), pen_up_ms=int(pen))

    say(f"\nSettings: {config.counts_per_mm_x:.4f} x {config.counts_per_mm_y:.4f} counts/mm, "
        f"drawing at {config.draw_speed:g} mm/s, pen {config.pen_down_ms}/{config.pen_up_ms} ms. "
        f"Try `plot test` next.")
    jobs.rest(plotter, config)
    plotter.close()


def _yes(answer: str) -> bool:
    return answer.strip().lower() in ("", "y", "yes")


def _choose(ask: Callable[[str], str], question: str, options: list[int], current: float) -> float:
    listed = ", ".join(str(o) for o in options)
    while True:
        answer = ask(f"{question} ({listed}; Enter keeps {current:g}): ").strip()
        if not answer:
            return current
        try:
            return float(answer)
        except ValueError:
            pass
