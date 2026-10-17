"""Setting the scale from the plotter's own rulers (no pen needed)."""

from collections.abc import Callable

from . import jobs, planner
from .config import Config
from .device import Plotter

# Two DAC positions comfortably inside the bed with the knobs as in the README.
RULER_POINTS = [(1200, 1500), (2900, 2600)]


def ruler_scale(readings: list[tuple[float, float]]) -> tuple[float, float]:
    """Counts per mm from ruler readings (inches) at the two RULER_POINTS. A ruler that
    counts down as the voltage goes up gives a negative scale, which flips that axis."""
    (ax, ay), (bx, by) = readings
    (cx0, cy0), (cx1, cy1) = RULER_POINTS
    if ax == bx or ay == by:
        raise ValueError("The two readings must differ on both rulers")
    return (cx1 - cx0) / ((bx - ax) * 25.4), (cy1 - cy0) / ((by - ay) * 25.4)


def with_rulers(plotter: Plotter, config: Config, ask: Callable[[str], str] = input,
                say: Callable[[str], None] = print):
    """Moves the pen to two spots, asks what the rulers read there, and saves the scale
    (keeping the paper centered where the pen parks)."""
    plotter.send("U")
    say("For each spot, read where the pen tip sits on the X ruler (along the bed's edge,"
        " the arm's position) and the Y ruler (on the arm), in inches.")
    readings = []
    for x, y in RULER_POINTS:
        target = complex(*config.to_mm(x, y))
        plotter.run(planner.move_to(config, jobs.position_mm(plotter, config), target).commands)
        plotter.wait_idle()
        readings.append((float(ask("  X ruler: ")), float(ask("  Y ruler: "))))
    per_mm_x, per_mm_y = ruler_scale(readings)
    say(f"X: {config.counts_per_mm_x:.4f} -> {per_mm_x:.4f} counts/mm, "
        f"Y: {config.counts_per_mm_y:.4f} -> {per_mm_y:.4f} counts/mm")
    config.save(**config.rescaled(per_mm_x, per_mm_y))
    say("Saved to plotter.toml. The paper stays centered where the pen parks.")
