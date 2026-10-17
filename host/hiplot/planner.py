"""Turns pen strokes into firmware commands.

The recorder's servos chase whatever voltage they're given, as fast as they can.
Jumping the voltage straight to a far point makes each axis race on its own, so
diagonals bend and corners overshoot. Instead each stroke gets a speed profile
(speed up, cruise, slow for corners, stop at the end) and is cut into short timed
straight segments that the firmware plays back on schedule.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass, field

import numpy as np

from .config import DAC_MAX, Config
from .geometry import Paths

# Corners sharper than this get a segment boundary exactly on the vertex.
CORNER_DEGREES = 10

# Longest single firmware segment (its duration is a 16-bit ms count).
MAX_SEGMENT_S = 30.0


class OutOfRange(Exception):
    pass


@dataclass
class Plan:
    commands: list[str] = field(default_factory=list)
    duration_ms: int = 0
    draw_mm: float = 0.0
    travel_mm: float = 0.0
    strokes: int = 0


def plan(paths: Paths, config: Config, start: complex, end: complex | None = None) -> Plan:
    """Commands that draw `paths` in order, starting with the pen (up) at `start` mm.
    Finishes with the pen up, moved to `end` if given."""
    builder = _Builder(config, start)
    builder.pen_up()
    for path in paths:
        builder.travel(path[0])
        builder.pen_down()
        builder.draw(path)
        builder.pen_up()
        builder.plan.strokes += 1
    if end is not None:
        builder.travel(end)
    return builder.plan


def move_to(config: Config, start: complex, target: complex) -> Plan:
    """A single pen-up move, without touching the pen."""
    builder = _Builder(config, start)
    builder.travel(target)
    return builder.plan


def glide(config: Config, start: complex, path: np.ndarray, speed: float) -> Plan:
    """Follows a polyline at `speed` without touching the pen, travelling to its start
    first if needed."""
    builder = _Builder(config, start)
    builder.travel(path[0])
    if len(path) > 1:
        builder.plan.travel_mm += float(np.abs(np.diff(path)).sum())
        builder.follow(path, speed)
    return builder.plan


class _Builder:
    def __init__(self, config: Config, start: complex):
        self.config = config
        self.position = start
        self.counts = config.to_counts(start.real, start.imag)
        self.pen_is_down: bool | None = None
        self.plan = Plan()

    def command(self, line: str, ms: int = 0):
        self.plan.commands.append(line)
        self.plan.duration_ms += ms

    def wait(self, ms: int):
        if ms > 0:
            self.command(f"W {ms}", ms)

    # MARK: - Pen

    def pen_down(self):
        self.wait(self.config.settle_ms)
        self.command("D")
        self.wait(self.config.pen_down_ms)
        self.pen_is_down = True

    def pen_up(self):
        if self.pen_is_down is False:
            return
        if self.pen_is_down:
            self.wait(self.config.settle_ms)
        self.command("U")
        self.wait(self.config.pen_up_ms)
        self.pen_is_down = False

    # MARK: - Motion

    def travel(self, target: complex):
        distance = abs(target - self.position)
        if distance < 0.01:
            return
        self.plan.travel_mm += distance
        self.follow(np.array([self.position, target]), self.config.travel_speed)

    def draw(self, path: np.ndarray):
        if len(path) > 1:
            self.plan.draw_mm += float(np.abs(np.diff(path)).sum())
            self.follow(path, self.config.draw_speed)

    def follow(self, path: np.ndarray, speed: float):
        profile = Profile(path, speed, self.config.accel, self.config.cornering)
        samples = profile.samples(self.config.sample_ms / 1000)

        emitted_ms = 0
        for i, (time_s, point) in enumerate(samples):
            counts = self._counts(point)
            if counts == self.counts:
                continue  # hasn't moved a whole count yet; the time rolls into the next segment
            total_ms = round(time_s * 1000)
            ms = total_ms - emitted_ms
            if ms == 0 and i < len(samples) - 1:
                continue  # too short to time; the next segment covers it
            self.command(f"M {counts[0]} {counts[1]} {ms}", ms)
            emitted_ms = total_ms
            self.counts = counts

        self.position = path[-1]

    def _counts(self, point: complex) -> tuple[int, int]:
        counts = self.config.to_counts(point.real, point.imag)
        if not (0 <= counts[0] <= DAC_MAX and 0 <= counts[1] <= DAC_MAX):
            raise OutOfRange(
                f"({point.real:.1f}, {point.imag:.1f}) mm needs DAC ({counts[0]}, {counts[1]}), "
                f"outside 0-{DAC_MAX}. Check origin and counts_per_mm in plotter.toml."
            )
        return counts


class Profile:
    """Speed along a polyline: starts and ends stopped, never accelerates harder than
    `accel`, and slows for corners using GRBL's junction deviation model (`cornering`
    is roughly how far, in mm, a corner may be cut at speed)."""

    def __init__(self, path: np.ndarray, speed: float, accel: float, cornering: float):
        deltas = np.diff(path)
        keep = np.abs(deltas) > 1e-9
        self.points = np.concatenate([path[:1], path[1:][keep]])
        deltas = deltas[keep]
        self.lengths = np.abs(deltas)
        self.units = deltas / self.lengths if len(deltas) else deltas
        self.accel = accel

        count = len(self.lengths)
        v = np.full(count + 1, float(speed))
        v[0] = v[-1] = 0.0
        self.corners: list[int] = []
        cos_corner = math.cos(math.radians(CORNER_DEGREES))
        for k in range(1, count):
            turn_cos = float((self.units[k - 1].conjugate() * self.units[k]).real)
            if turn_cos < cos_corner:
                self.corners.append(k)
            junction_cos = -turn_cos
            if junction_cos > 0.9999:
                v[k] = 0.0  # reversal
            elif junction_cos > -0.9999:
                sin_half = math.sqrt(0.5 * (1 - junction_cos))
                v[k] = min(speed, math.sqrt(accel * cornering * sin_half / (1 - sin_half)))

        # Make every speed reachable from its neighbors within the acceleration limit.
        for k in range(count - 1, -1, -1):
            v[k] = min(v[k], math.sqrt(v[k + 1] ** 2 + 2 * accel * self.lengths[k]))
        for k in range(1, count + 1):
            v[k] = min(v[k], math.sqrt(v[k - 1] ** 2 + 2 * accel * self.lengths[k - 1]))

        # Per segment: (v0, peak, v1, t_accel, t_cruise, t_decel, d_accel, d_cruise).
        self.segments = []
        self.starts = []
        t = 0.0
        for k in range(count):
            v0, v1, length = v[k], v[k + 1], self.lengths[k]
            peak = min(speed, math.sqrt((2 * accel * length + v0 ** 2 + v1 ** 2) / 2))
            peak = max(peak, v0, v1)
            d_accel = (peak ** 2 - v0 ** 2) / (2 * accel)
            d_decel = (peak ** 2 - v1 ** 2) / (2 * accel)
            d_cruise = max(0.0, length - d_accel - d_decel)
            t_accel = (peak - v0) / accel
            t_decel = (peak - v1) / accel
            t_cruise = d_cruise / peak if peak > 0 else 0.0
            self.starts.append(t)
            self.segments.append((v0, peak, v1, t_accel, t_cruise, t_decel, d_accel, d_cruise))
            t += t_accel + t_cruise + t_decel
        self.duration = t

    def position(self, time: float) -> complex:
        if not self.segments:
            return complex(self.points[0])
        k = max(0, min(bisect_right(self.starts, time) - 1, len(self.segments) - 1))
        v0, peak, _, t_accel, t_cruise, t_decel, d_accel, d_cruise = self.segments[k]
        tau = time - self.starts[k]
        if tau <= t_accel:
            distance = v0 * tau + 0.5 * self.accel * tau ** 2
        elif tau <= t_accel + t_cruise:
            distance = d_accel + peak * (tau - t_accel)
        else:
            tau_d = min(tau - t_accel - t_cruise, t_decel)
            distance = d_accel + d_cruise + peak * tau_d - 0.5 * self.accel * tau_d ** 2
        distance = min(max(distance, 0.0), self.lengths[k])
        return complex(self.points[k] + self.units[k] * distance)

    def samples(self, step: float) -> list[tuple[float, complex]]:
        """(time, point) every `step` seconds, plus every sharp corner, plus the end.
        Long straight cruises need only their endpoints."""
        uniform = np.arange(step, self.duration, step)
        keep = np.ones(len(uniform), dtype=bool)
        extra: list[float] = []

        for k, (_, _, _, t_accel, t_cruise, _, _, _) in enumerate(self.segments):
            if t_cruise > 2 * step:
                begin = self.starts[k] + t_accel
                finish = begin + t_cruise
                keep[np.searchsorted(uniform, begin, "right"):np.searchsorted(uniform, finish, "left")] = False
                extra += np.arange(begin, finish, MAX_SEGMENT_S).tolist() + [finish]

        # Corners land exactly on their vertex; drop uniform samples right next to one.
        corner_times = np.array([self.starts[k] for k in self.corners])
        if len(corner_times):
            nearest = np.clip(np.searchsorted(corner_times, uniform), 1, len(corner_times)) - 1
            following = np.clip(nearest + 1, 0, len(corner_times) - 1)
            gap = np.minimum(np.abs(uniform - corner_times[nearest]), np.abs(uniform - corner_times[following]))
            keep &= gap > 0.002

        # Corners first, so a tie keeps the exact vertex (the sort below is stable).
        others = keep.sum() + len(extra)
        times = np.concatenate([corner_times, uniform[keep], extra])
        corner = np.concatenate([np.ones(len(corner_times), dtype=bool), np.zeros(others, dtype=bool)])
        vertex = np.concatenate([self.corners, np.full(others, -1)]).astype(int)
        valid = (times > 0) & (times < self.duration - 1e-6)
        order = np.argsort(times[valid], kind="stable")
        times, corner, vertex = times[valid][order], corner[valid][order], vertex[valid][order]

        result = []
        for t, is_corner, k in zip(times.tolist(), corner.tolist(), vertex.tolist()):
            if result and t - result[-1][0] < 1e-9:
                continue  # the same moment twice (a cruise ending on a corner)
            result.append((t, complex(self.points[k]) if is_corner else self.position(t)))
        result.append((self.duration, complex(self.points[-1])))
        return result
