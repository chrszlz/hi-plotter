"""Text in any font.

Hershey fonts (futural, scripts, timesr, ...) are single-stroke: each letter is drawn
as a pen would write it, so they look best and plot fastest. Any font installed on the
Mac (Helvetica, Avenir, Georgia, ...) works too, drawn as letter outlines, with an
optional hatch fill.
"""

import difflib
import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import vpype as vp
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTCollection, TTFont

from .geometry import Paths, hatch

FONT_DIRS = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}

# Hershey glyphs are centered vertically: capitals start this far (in font sizes)
# above vpype's text origin.
HERSHEY_CAP_TOP = 0.375

# Some system fonts have harmless quirks fontTools likes to mention.
logging.getLogger("fontTools").setLevel(logging.ERROR)


@dataclass(frozen=True)
class SystemFont:
    name: str
    path: str
    index: int = 0


class FontNotFound(Exception):
    pass


# MARK: - Finding fonts


@lru_cache
def system_fonts() -> dict[str, SystemFont]:
    """Installed fonts by lowercase full name ("helvetica bold")."""
    fonts: dict[str, SystemFont] = {}
    for directory in FONT_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() not in FONT_SUFFIXES:
                continue
            try:
                faces = TTCollection(str(path), lazy=True).fonts if path.suffix.lower() == ".ttc" \
                    else [TTFont(str(path), lazy=True)]
                for index, face in enumerate(faces):
                    name = face["name"].getBestFullName()
                    if name and not name.startswith(".") and ("glyf" in face or "CFF " in face):
                        fonts.setdefault(name.lower(), SystemFont(name, str(path), index))
            except Exception:
                continue  # unreadable or bitmap-only fonts
    return fonts


def find(name: str) -> str | SystemFont:
    """A Hershey font name, or an installed font matched by name, or a font file path."""
    if name in vp.FONT_NAMES:
        return name
    path = Path(name).expanduser()
    if path.suffix.lower() in FONT_SUFFIXES and path.exists():
        return SystemFont(path.stem, str(path))

    fonts = system_fonts()
    wanted = name.lower().strip()
    if wanted in fonts:
        return fonts[wanted]
    # "avenir next bold" -> "Avenir Next Bold"; "helvetica" -> "Helvetica"; shortest wins.
    words = wanted.replace("-", " ").split()
    matches = [f for key, f in fonts.items() if all(w in key.replace("-", " ").split() for w in words)]
    if not matches:
        matches = [f for key, f in fonts.items() if all(w in key for w in words)]
    if matches:
        return min(matches, key=lambda f: len(f.name))

    suggestions = difflib.get_close_matches(wanted, list(fonts) + list(vp.FONT_NAMES), n=4, cutoff=0.5)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else " Run `plot fonts` for the list."
    raise FontNotFound(f"No font called {name!r}.{hint}")


def names() -> list[tuple[str, str]]:
    """(name, kind) for every usable font, single-stroke first."""
    hershey = [(n, "single-stroke") for n in vp.FONT_NAMES]
    system = sorted(((f.name, "outline") for f in system_fonts().values()), key=lambda f: f[0].lower())
    return hershey + system


# MARK: - Text

# Typography the Hershey fonts don't have, as plain ASCII.
PLAIN = str.maketrans({
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2018": "'", "\u2019": "'", "\u201a": "'",
    "\u2014": "-", "\u2013": "-", "\u2212": "-", "\u2026": "...", "\u00a0": " ", "\u2022": "*",
    "\u00d7": "x", "\t": "    ",
})


def prepare(content: str, face: "str | SystemFont") -> str:
    """Tabs become spaces. For single-stroke fonts, which only have plain ASCII, smart
    quotes and dashes become plain ones and accents are dropped (é -> e)."""
    if not isinstance(face, str):
        return content.replace("\t", "    ")
    decomposed = unicodedata.normalize("NFKD", content.translate(PLAIN))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def missing(content: str, font: str) -> str:
    """The characters in `content` that `font` can't draw, in order, once each."""
    face = find(font)
    if isinstance(face, str):
        drawable = lambda c: 32 <= ord(c) < 127
    else:
        cmap = _open(face.path, face.index).getBestCmap() or {}
        drawable = lambda c: ord(c) in cmap
    gaps = [c for c in prepare(content, face) if not c.isspace() and not drawable(c)]
    return "".join(dict.fromkeys(gaps))


def text(content: str, size: float, font: str = "futural", width: float | None = None,
         align: str = "left", line_spacing: float = 1.4, fill: float | None = None) -> Paths:
    """Lays out text. `size` is the font size in mm (capitals are about 0.7 of it).
    Wraps at `width` mm if given, and on newlines. `fill` hatches outline fonts with
    lines that far apart (mm).

    The top of the first line's capitals is at y = 0 and lines go downward. "left" text
    starts at x = 0; "center" and "right" line up within `width`, or around x = 0.
    """
    face = find(font)
    renderer = _Hershey(face, size) if isinstance(face, str) else _Outline(face, size)
    content = prepare(content, face)

    lines: list[str] = []
    for paragraph in content.split("\n"):
        lines += _wrap(paragraph, width, renderer.width) if width else [paragraph]

    paths: Paths = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        strokes = renderer.line(line)
        line_width = renderer.width(line)
        if align == "center":
            shift = ((width or 0) - line_width) / 2 if width else -line_width / 2
        elif align == "right":
            shift = (width or 0) - line_width
        else:
            shift = 0.0
        offset = complex(shift, -i * size * line_spacing)
        paths += [s + offset for s in strokes]

    if fill and isinstance(face, SystemFont):
        paths += hatch(paths, fill)
    return paths


def _wrap(paragraph: str, width: float, measure) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in paragraph.split():
        candidate = f"{current} {word}".strip()
        if current and measure(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


class _Hershey:
    def __init__(self, name: str, size: float):
        self.name = name
        self.size = size

    def line(self, content: str) -> Paths:
        top = self.size * HERSHEY_CAP_TOP
        rendered = vp.text_line(content, font_name=self.name, size=self.size)
        return [s.real - 1j * (s.imag + top) for s in rendered]

    def width(self, content: str) -> float:
        rendered = vp.text_line(content, font_name=self.name, size=self.size)
        return 0.0 if rendered.is_empty() else rendered.bounds()[2]


class _Outline:
    def __init__(self, face: SystemFont, size: float):
        font = _open(face.path, face.index)
        self.glyphs = font.getGlyphSet()
        self.cmap = font.getBestCmap() or {}
        units = font["head"].unitsPerEm
        self.scale = size / units
        os2 = font["OS/2"] if "OS/2" in font else None
        self.cap_height = getattr(os2, "sCapHeight", 0) or 0.7 * units
        # Curves are cut into straight pieces about this long (font units).
        self.step = 0.25 / self.scale

    def _glyph(self, char: str) -> str | None:
        return self.cmap.get(ord(char))

    def width(self, content: str) -> float:
        total = 0
        for char in content:
            name = self._glyph(char) or self._glyph("?")
            total += self.glyphs[name].width if name else 0
        return total * self.scale

    def line(self, content: str) -> Paths:
        paths: Paths = []
        x = 0.0
        for char in content:
            name = self._glyph(char) or self._glyph("?")
            if not name:
                continue
            pen = _FlattenPen(self.glyphs, self.step)
            self.glyphs[name].draw(pen)
            for contour in pen.contours:
                if len(contour) > 1:
                    points = np.array(contour)
                    paths.append(((points.real + x) + 1j * (points.imag - self.cap_height)) * self.scale)
            x += self.glyphs[name].width
        return paths


@lru_cache(maxsize=16)
def _open(path: str, index: int) -> TTFont:
    return TTFont(path, fontNumber=index) if path.lower().endswith(".ttc") else TTFont(path)


class _FlattenPen(BasePen):
    """Collects glyph outlines as polylines, cutting curves into short straight pieces."""

    def __init__(self, glyph_set, step: float):
        super().__init__(glyph_set)
        self.step = step
        self.contours: list[list[complex]] = []

    def _moveTo(self, point):
        self.contours.append([complex(*point)])

    def _lineTo(self, point):
        self.contours[-1].append(complex(*point))

    def _curveToOne(self, p1, p2, p3):
        p0 = self.contours[-1][-1]
        c1, c2, c3 = complex(*p1), complex(*p2), complex(*p3)
        length = abs(c1 - p0) + abs(c2 - c1) + abs(c3 - c2)
        count = max(2, min(64, math.ceil(length / self.step)))
        for t in np.linspace(0, 1, count + 1)[1:]:
            u = 1 - t
            self.contours[-1].append(u ** 3 * p0 + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t ** 3 * c3)

    def _closePath(self):
        contour = self.contours[-1]
        if contour[0] != contour[-1]:
            contour.append(contour[0])


def parse_size(value: str | float) -> float:
    """A length in mm from "12", "12mm", "1.5cm", "0.5in" or "24pt"."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*([0-9.]+)\s*(mm|cm|in|pt|\")?\s*", value)
    if not match:
        raise ValueError(f"Not a size: {value!r} (try 12mm, 0.5in or 24pt)")
    number, unit = float(match.group(1)), match.group(2) or "mm"
    return number * {"mm": 1, "cm": 10, "in": 25.4, '"': 25.4, "pt": 25.4 / 72}[unit]
