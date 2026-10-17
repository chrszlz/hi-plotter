"""Line drawings (dark lines on a light background) as pen strokes: every line is
thinned to its centerline and followed, so each one is drawn once, down its middle,
instead of being shaded in."""

import io

import numpy as np
import shapely
from PIL import Image, ImageFilter, ImageOps
from skimage.morphology import remove_small_objects, skeletonize

from .geometry import Paths

# The 8 neighbors of a pixel, as (row, column) offsets.
NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def load(data: bytes) -> Image.Image:
    """The picture in grayscale, upright, with transparency counted as white."""
    picture = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if picture.mode in ("RGBA", "LA", "P"):
        picture = picture.convert("RGBA")
        picture = Image.alpha_composite(Image.new("RGBA", picture.size, "white"), picture)
    return picture.convert("L")


def grayscale(data: bytes) -> np.ndarray:
    """Pixels from 0 (black) to 1 (white)."""
    return np.asarray(load(data), float) / 255


def is_line_art(gray: np.ndarray) -> bool:
    """Mostly white with dark lines and few in-between tones, like a drawing or a scan
    of one (rather than a photo)."""
    dark = (gray < 0.5).mean()
    middle = ((gray > 0.25) & (gray < 0.75)).mean()
    return dark < 0.3 and middle < 0.1


def trace(data: bytes, width: float, height: float, threshold: float = 0.5,
          smoothing_px: float = 0.8, shortest_mm: float = 0.25) -> Paths:
    """The picture's lines as strokes, fitted into width x height mm with its
    lower-left corner at (0, 0)."""
    # A touch of blur keeps JPEG noise from turning into whiskers.
    gray = np.asarray(load(data).filter(ImageFilter.GaussianBlur(0.8)), float) / 255
    rows, columns = gray.shape
    mm_per_px = min(width / columns, height / rows)

    ink = remove_small_objects(gray < threshold, max_size=8)
    skeleton = skeletonize(ink)

    strokes = []
    for pixels in _walk(skeleton):
        line = np.array(pixels, dtype=float)
        if len(line) >= 2:
            strokes.append(shapely.LineString(line[:, ::-1]))  # (column, row) = (x, y down)
    strokes = shapely.simplify(np.array(strokes, dtype=object), smoothing_px) if strokes else []

    paths: Paths = []
    for stroke in strokes:
        xy = shapely.get_coordinates(stroke)
        path = (xy[:, 0] + 1j * (rows - xy[:, 1])) * mm_per_px
        if np.abs(np.diff(path)).sum() >= shortest_mm:
            paths.append(path)
    return paths


def _walk(skeleton: np.ndarray) -> list[list[tuple[int, int]]]:
    """Splits a 1-pixel-wide skeleton into chains of pixels: each runs between line
    ends and junctions, and closed loops come out as one chain each."""
    pixels = set(zip(*np.nonzero(skeleton)))

    def neighbors(p):
        r, c = p
        return [q for q in ((r + dr, c + dc) for dr, dc in NEIGHBORS) if q in pixels]

    links = {p: neighbors(p) for p in pixels}
    used: set[tuple] = set()

    def edge(a, b):
        return (a, b) if a < b else (b, a)

    def follow(start, step):
        chain = [start, step]
        used.add(edge(start, step))
        previous, current = start, step
        while len(links[current]) == 2:
            following = next((q for q in links[current] if q != previous and edge(current, q) not in used), None)
            if following is None:
                break
            used.add(edge(current, following))
            chain.append(following)
            previous, current = current, following
        return chain

    chains = []
    # Start from line ends and junctions...
    for p in pixels:
        if len(links[p]) != 2:
            for q in links[p]:
                if edge(p, q) not in used:
                    chains.append(follow(p, q))
    # ...then whatever is left is closed loops.
    for p in pixels:
        for q in links[p]:
            if edge(p, q) not in used:
                chains.append(follow(p, q))
    return chains
