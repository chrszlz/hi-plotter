"""Planning a drawing into a job and streaming it, shared by the CLI and the web UI."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import geometry, planner, preview
from .config import Config
from .device import Plotter
from .sources import Drawing


@dataclass
class Job:
    drawing: Drawing
    plan: planner.Plan
    start: complex
    # Planned elapsed ms after each command, for progress.
    elapsed_ms: list[int] = field(default_factory=list)

    @property
    def summary(self) -> str:
        p = self.plan
        return (f"{self.drawing.name}: {p.strokes} strokes, {p.draw_mm / 1000:.2f} m of ink, "
                f"{p.travel_mm / 1000:.2f} m of travel, about {duration(p.duration_ms)}")

    def preview_strokes(self, config: Config):
        return preview.from_commands(self.plan.commands, config, config.to_counts(self.start.real, self.start.imag))


def prepare(drawing: Drawing, config: Config, start: complex = 0j) -> Job:
    """Orders the strokes and plans the motion, starting from the pen's position (mm)
    and finishing at the paper origin."""
    paths = geometry.optimize(drawing.paths, start=start)
    return from_plan(drawing, planner.plan(paths, config, start=start, end=0j), start)


def from_plan(drawing: Drawing, plan: planner.Plan, start: complex) -> Job:
    elapsed, total = [], 0
    for line in plan.commands:
        if line[0] in "MW":
            total += int(line.split()[-1])
        elapsed.append(total)
    return Job(drawing, plan, start, elapsed)


def position_mm(plotter: Plotter, config: Config) -> complex:
    status = plotter.status()
    return complex(*config.to_mm(status.x, status.y))


class Stopped(Exception):
    pass


def stream(plotter: Plotter, job: Job, progress: Callable[[float, float], None] | None = None,
           stop: threading.Event | None = None):
    """Sends the job. `progress(fraction, seconds_left)` is called as it goes. Setting
    `stop` (or Ctrl-C) halts the pen and lifts it, raising Stopped."""
    total = max(job.elapsed_ms[-1] if job.elapsed_ms else 0, 1)
    started = time.monotonic()
    last = 0.0
    sent_ms = 0

    def report(sent: int | None = None):
        # The firmware plays commands on schedule, so time says where the pen is; what's
        # been sent caps it, in case the pen is waiting on the Mac.
        nonlocal last, sent_ms
        if stop is not None and stop.is_set():
            raise Stopped()
        if sent is not None:
            sent_ms = job.elapsed_ms[sent - 1]
        now = time.monotonic()
        if progress and now - last >= 0.25:
            last = now
            done_ms = min(sent_ms, (now - started) * 1000)
            progress(done_ms / total, (total - done_ms) / 1000)

    try:
        plotter.run(job.plan.commands, report)
        while not plotter.status().idle:
            report()
            time.sleep(0.2)
        if progress:
            progress(1.0, 0.0)
    except (Stopped, KeyboardInterrupt):
        plotter.stop()
        raise Stopped() from None


def duration(ms: float) -> str:
    seconds = round(ms / 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"
