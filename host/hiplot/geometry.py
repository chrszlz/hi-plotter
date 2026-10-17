"""Drawings as polylines in paper millimeters (origin lower-left, y up).

A drawing is a list of numpy arrays of complex numbers, one array per pen-down
stroke: x is the real part, y the imaginary part.
"""

import math

import numpy as np
import vpype as vp

Paths = list[np.ndarray]


# MARK: - Shapes


def circle(center: complex, radius: float, segment_mm: float = 0.5) -> np.ndarray:
    count = max(16, math.ceil(2 * math.pi * radius / segment_mm))
    return center + radius * np.exp(1j * np.linspace(0, 2 * math.pi, count + 1))


def polygon(points: list[complex], closed: bool = True) -> np.ndarray:
    return np.array(points + points[:1] if closed else points, dtype=complex)


def hatch(paths: Paths, spacing: float, angle: float = 45) -> Paths:
    """Parallel lines `spacing` mm apart filling the closed shapes in `paths`
    (even-odd, so letter counters and holes stay empty)."""
    turn = np.exp(-1j * math.radians(angle))  # rotate so the hatch lines run along x
    closed = [p * turn for p in paths if len(p) > 2 and abs(p[0] - p[-1]) < 1e-6]
    if not closed:
        return []

    starts = np.concatenate([p[:-1] for p in closed])
    ends = np.concatenate([p[1:] for p in closed])
    y0, y1 = starts.imag, ends.imag
    lines: Paths = []
    for i, y in enumerate(np.arange(min(y0.min(), y1.min()) + spacing / 2, max(y0.max(), y1.max()), spacing)):
        crossing = (y0 <= y) != (y1 <= y)
        t = (y - y0[crossing]) / (y1[crossing] - y0[crossing])
        xs = np.sort(starts.real[crossing] + t * (ends.real[crossing] - starts.real[crossing]))
        for left, right in xs[: len(xs) // 2 * 2].reshape(-1, 2):
            if right - left > 1e-6:
                line = np.array([left + 1j * y, right + 1j * y])
                lines.append((line if i % 2 == 0 else line[::-1]) / turn)
    return lines


# MARK: - Layout


def bounds(paths: Paths) -> tuple[float, float, float, float]:
    points = np.concatenate(paths)
    return (points.real.min(), points.imag.min(), points.real.max(), points.imag.max())


def translate(paths: Paths, offset: complex) -> Paths:
    return [p + offset for p in paths]


def scale(paths: Paths, factor: float, about: complex = 0) -> Paths:
    return [(p - about) * factor + about for p in paths]


def rotate(paths: Paths, degrees: int) -> Paths:
    """Counterclockwise, in quarter turns."""
    return [p * 1j ** (round(degrees / 90) % 4) for p in paths]


def fit(paths: Paths, box: tuple[float, float, float, float], grow: bool = True) -> Paths:
    """Scales (keeping proportions) and centers the drawing inside box (x0, y0, x1, y1).
    With grow=False it only ever shrinks."""
    x0, y0, x1, y1 = bounds(paths)
    bx0, by0, bx1, by1 = box
    factor = min((bx1 - bx0) / max(x1 - x0, 1e-9), (by1 - by0) / max(y1 - y0, 1e-9))
    if not grow:
        factor = min(factor, 1.0)
    center = complex((x0 + x1) / 2, (y0 + y1) / 2)
    target = complex((bx0 + bx1) / 2, (by0 + by1) / 2)
    return [(p - center) * factor + target for p in paths]


def inside(paths: Paths, box: tuple[float, float, float, float], tolerance: float = 1e-6) -> bool:
    x0, y0, x1, y1 = bounds(paths)
    bx0, by0, bx1, by1 = box
    return (x0 >= bx0 - tolerance and y0 >= by0 - tolerance
            and x1 <= bx1 + tolerance and y1 <= by1 + tolerance)


# MARK: - Optimization


def optimize(paths: Paths, start: complex = 0, merge_mm: float = 0.2) -> Paths:
    """Joins strokes whose ends touch, then orders them (flipping where it helps) to
    keep pen-up travel short: greedy nearest neighbor starting from `start`."""
    paths = [p for p in (_dedupe(p) for p in paths) if len(p) > 0]
    if not paths:
        return []

    collection = vp.LineCollection(paths)
    collection.merge(tolerance=merge_mm, flip=True)
    remaining = vp.LineIndex(list(collection), reverse=True)

    ordered: Paths = []
    position = start
    while len(remaining) > 0:
        index, reverse = remaining.find_nearest(position)
        line = remaining.pop(index)
        if reverse:
            line = line[::-1]
        ordered.append(line)
        position = line[-1]
    return ordered


def _dedupe(path: np.ndarray, tolerance: float = 1e-3) -> np.ndarray:
    """Drops consecutive points closer than tolerance."""
    if len(path) < 2:
        return path
    keep = np.concatenate([[True], np.abs(np.diff(path)) > tolerance])
    return path[keep]


def pen_up_length(paths: Paths, start: complex = 0) -> float:
    total, position = 0.0, start
    for p in paths:
        total += abs(p[0] - position)
        position = p[-1]
    return total
