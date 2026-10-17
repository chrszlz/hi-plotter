"""Everything the plotter can draw from, laid out on the paper.

`load("Hello")` writes text, `load("drawing.svg")` draws a file. Files are recognized
by extension: SVG, G-code, HPGL (Inkscape can save it), plain text, and images
(drawn as crosshatching).
"""

import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import vpype as vp
from PIL import Image, ImageOps

from . import fonts, geometry, lineart
from .config import Config
from .geometry import Paths

PX_PER_MM = 96 / 25.4  # vpype works in CSS pixels

KINDS = {
    ".svg": "svg",
    ".gcode": "gcode", ".nc": "gcode", ".ngc": "gcode", ".gc": "gcode", ".g": "gcode", ".tap": "gcode",
    ".hpgl": "hpgl", ".hpg": "hpgl", ".hgl": "hpgl", ".plt": "hpgl",
    ".txt": "text", ".text": "text", ".md": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".bmp": "image",
    ".webp": "image", ".tif": "image", ".tiff": "image",
}

# Whether each kind is scaled to fill the printable area unless told otherwise.
# G-code and HPGL are already in real millimeters; text has a font size.
FIT_BY_DEFAULT = {"text": False, "svg": True, "gcode": False, "hpgl": False, "image": True}


class SourceError(Exception):
    pass


@dataclass
class TextStyle:
    font: str = "futural"
    size: float = 10.0          # mm
    align: str = "left"
    line_spacing: float = 1.4
    width: float | None = None  # wrap width in mm; default: the printable width
    fill: bool = False          # hatch-fill outline fonts


@dataclass
class Layout:
    fit: bool | None = None     # None: the source's default (see FIT_BY_DEFAULT)
    scale: float = 1.0
    rotate: int = 0             # degrees counterclockwise, quarter turns
    at: complex | None = None   # top-left corner in mm
    hatch: float = 0.8          # mm between hatch lines (images, filled text)
    image: str = "auto"         # pictures: "lines" traces line art, "hatch" shades; auto picks


@dataclass
class Drawing:
    paths: Paths
    kind: str
    name: str
    notes: list[str] = field(default_factory=list)


# MARK: - Loading


def kind_of(name: str) -> str | None:
    return KINDS.get(Path(name).suffix.lower())


def is_file_name(source: str) -> bool:
    """Whether `source` means a file: it exists, or it has a drawable extension and no
    spaces (so "see notes.txt" is text but "notes.txt" is a file, even a missing one)."""
    if not kind_of(source) or len(source) > 1024 or "\n" in source:
        return False
    return Path(source).expanduser().is_file() or not any(c.isspace() for c in source)


def load(source: str, config: Config, style: TextStyle | None = None, layout: Layout | None = None) -> Drawing:
    """A file path (see is_file_name) or literal text."""
    if not is_file_name(source):
        return text(source, config, style, layout)
    path = Path(source).expanduser()
    if not path.is_file():
        raise SourceError(f"No such file: {source}")
    return load_bytes(path.read_bytes(), path.name, config, style, layout)


def text(content: str, config: Config, style: TextStyle | None = None, layout: Layout | None = None,
         name: str = "Text") -> Drawing:
    style, layout = style or TextStyle(), layout or Layout()
    drawing = lay_out(_text(content, config, style, layout), "text", name, config, layout)
    gaps = fonts.missing(content, style.font)
    if gaps:
        drawing.notes.append(f"{style.font} can't draw {gaps}; those are skipped. An installed font such as "
                             f"Arial Unicode MS or Hiragino Sans has more characters.")
    return drawing


def load_bytes(data: bytes, name: str, config: Config, style: TextStyle | None = None,
               layout: Layout | None = None) -> Drawing:
    """File contents, typed by the file name's extension."""
    style, layout = style or TextStyle(), layout or Layout()
    kind = kind_of(name)
    if kind is None:
        raise SourceError(f"Don't know how to draw {name}. Try SVG, G-code, HPGL, text or an image.")

    if kind == "text":
        return text(data.decode(errors="replace"), config, style, layout, name)
    elif kind == "svg":
        paths = svg(data)
    elif kind == "gcode":
        paths = gcode(data.decode(errors="replace"))
    elif kind == "hpgl":
        paths = hpgl(data.decode(errors="replace"))
    else:
        # Hatched at its final size (the hatch spacing is in paper mm), so scaling is
        # done here rather than afterwards.
        width, height = _printable_size(config, layout.rotate)
        style = layout.image
        if style == "auto":
            style = "lines" if lineart.is_line_art(lineart.grayscale(data)) else "hatch"
        if style == "lines":
            paths = lineart.trace(data, width * layout.scale, height * layout.scale)
        else:
            paths = image(data, width * layout.scale, height * layout.scale, layout.hatch)
        layout = Layout(fit=False if layout.fit is None else layout.fit, scale=1.0,
                        rotate=layout.rotate, at=layout.at, hatch=layout.hatch, image=style)
    if not paths:
        raise SourceError(f"{name} has nothing to draw")
    return lay_out(paths, kind, name, config, layout)


def _printable_size(config: Config, rotate: int) -> tuple[float, float]:
    """The printable width and height as seen by a drawing before it's rotated."""
    x0, y0, x1, y1 = config.printable
    quarter_turned = round(rotate / 90) % 2 == 1
    return (y1 - y0, x1 - x0) if quarter_turned else (x1 - x0, y1 - y0)


def _text(content: str, config: Config, style: TextStyle, layout: Layout) -> Paths:
    width = style.width or _printable_size(config, layout.rotate)[0] / layout.scale
    try:
        return fonts.text(content.strip("\n"), style.size, style.font, width, style.align,
                          style.line_spacing, layout.hatch if style.fill else None)
    except fonts.FontNotFound as error:
        raise SourceError(str(error)) from error


# MARK: - Layout


def lay_out(paths: Paths, kind: str, name: str, config: Config, layout: Layout) -> Drawing:
    """Rotates, scales and positions a drawing on the paper. Shrinks it to fit (with a
    note) if it would run off the paper, unless fitting was turned off."""
    drawing = Drawing(paths, kind, name)
    if not paths:
        return drawing

    paths = geometry.rotate(paths, layout.rotate)
    if layout.scale != 1 and kind != "image":
        paths = geometry.scale(paths, layout.scale)

    x0, y0, x1, y1 = config.printable
    fit = FIT_BY_DEFAULT[kind] if layout.fit is None else layout.fit
    if fit:
        paths = geometry.fit(paths, config.printable)
    elif layout.at is not None:
        bx0, _, _, by1 = geometry.bounds(paths)
        paths = geometry.translate(paths, layout.at - complex(bx0, by1))
    elif kind == "text" and layout.rotate % 360 == 0:
        paths = geometry.translate(paths, complex(x0, y1))  # keeps alignment within the width
    elif kind == "text":
        bx0, _, _, by1 = geometry.bounds(paths)
        paths = geometry.translate(paths, complex(x0 - bx0, y1 - by1))
    elif kind == "svg":
        paths = geometry.translate(paths, complex(0, config.paper_height))  # page top-left on paper top-left
    elif kind == "image":
        bx0, by0, bx1, by1 = geometry.bounds(paths)
        paths = geometry.translate(paths, complex(config.paper_width - bx0 - bx1, config.paper_height - by0 - by1) / 2)

    paper = (0, 0, config.paper_width, config.paper_height)
    if not geometry.inside(paths, paper):
        if layout.fit is False:
            bx0, by0, bx1, by1 = geometry.bounds(paths)
            raise SourceError(f"{name} ({bx1 - bx0:.0f} x {by1 - by0:.0f} mm) runs off the "
                              f"{config.paper_width:g} x {config.paper_height:g} mm paper")
        paths = geometry.fit(paths, config.printable, grow=False)
        drawing.notes.append("Shrunk to fit the paper.")

    drawing.paths = paths
    return drawing


# MARK: - File formats


def svg(data: bytes, quantization_mm: float = 0.1) -> Paths:
    """Every path in an SVG (strokes and the outlines of fills), in mm, with the page's
    top-left corner at (0, 0) and the page below it."""
    lines, _, height = vp.read_svg(io.StringIO(data.decode(errors="replace")),
                                   quantization=quantization_mm * PX_PER_MM)
    return [line.real / PX_PER_MM - 1j * line.imag / PX_PER_MM for line in lines] if height else []


def gcode(content: str) -> Paths:
    """G0/G1/G2/G3 moves in mm or inches (G20/G21), absolute or relative (G90/G91).
    The pen is down when Z <= 0 or after M3/M4 (up after M5). Files with neither
    draw on G1-G3 and travel on G0."""
    lines = [re.sub(r"\(.*?\)", "", raw).split(";")[0] for raw in content.splitlines()]
    code = "\n".join(lines)
    has_pen_info = re.search(r"(?i)(?<![a-z])(Z\s*[-+.\d]|M0*[345](?!\d))", code) is not None
    units, absolute, motion = 1.0, True, 0
    position, pen_down = 0j, False
    paths: Paths = []
    current: list[complex] | None = None

    for line in lines:
        words = re.findall(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))", line)
        params: dict[str, float] = {}
        for letter, value in words:
            letter, number = letter.upper(), float(value)
            if letter == "G":
                code = int(number)
                if code in (0, 1, 2, 3):
                    motion = code
                elif code == 20:
                    units = 25.4
                elif code == 21:
                    units = 1.0
                elif code == 90:
                    absolute = True
                elif code == 91:
                    absolute = False
            elif letter == "M" and int(number) in (3, 4, 5):
                pen_down = int(number) != 5
            else:
                params[letter] = number

        if "Z" in params:
            pen_down = params["Z"] * units <= 0
        if "X" not in params and "Y" not in params:
            continue

        x, y = (params.get(axis, 0.0) * units for axis in "XY")
        if absolute:
            target = complex(x if "X" in params else position.real, y if "Y" in params else position.imag)
        else:
            target = position + complex(x, y)
        drawing = pen_down if has_pen_info else motion != 0
        if not drawing:
            current = None
        else:
            if current is None:
                current = [position]
                paths.append(current)
            if motion in (2, 3) and ("I" in params or "J" in params):
                center = position + complex(params.get("I", 0), params.get("J", 0)) * units
                current += _arc(position, target, center, clockwise=motion == 2)[1:]
            else:
                current.append(target)
        position = target

    return [np.array(p) for p in paths if len(p) > 1]


def _arc(start: complex, end: complex, center: complex, clockwise: bool, segment_mm: float = 0.5) -> list[complex]:
    radius = abs(start - center)
    a0, a1 = np.angle(start - center), np.angle(end - center)
    sweep = (a1 - a0) % (2 * math.pi)
    if clockwise:
        sweep -= 2 * math.pi
    if abs(sweep) < 1e-9:
        sweep = -2 * math.pi if clockwise else 2 * math.pi  # full circle
    count = max(2, math.ceil(abs(sweep) * radius / segment_mm))
    points = [center + radius * np.exp(1j * (a0 + sweep * i / count)) for i in range(count + 1)]
    points[-1] = end
    return points


def hpgl(content: str) -> Paths:
    """PU/PD/PA/PR with coordinates in plotter units (40 per mm), as Inkscape saves."""
    units = 40.0
    absolute, position, pen_down = True, 0j, False
    paths: list[list[complex]] = []
    current: list[complex] | None = None

    for op, args in re.findall(r"([A-Za-z]{2})([^A-Za-z;]*)", content):
        op = op.upper()
        if op == "PU":
            pen_down = False
        elif op == "PD":
            pen_down = True
        elif op == "PA":
            absolute = True
        elif op == "PR":
            absolute = False
        else:
            continue
        if not pen_down:
            current = None

        numbers = [float(n) for n in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", args)]
        for x, y in zip(numbers[::2], numbers[1::2]):
            step = complex(x, y) / units
            target = step if absolute else position + step
            if pen_down:
                if current is None:
                    current = [position]
                    paths.append(current)
                current.append(target)
            position = target

    return [np.array(p) for p in paths if len(p) > 1]


def image(data: bytes, width: float, height: float, spacing: float = 0.8) -> Paths:
    """A picture as crosshatching, fitted into width x height mm: light areas get one
    direction of lines, darker areas up to four. Transparent areas count as white."""
    picture = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if picture.mode in ("RGBA", "LA", "P"):
        picture = picture.convert("RGBA")
        background = Image.new("RGBA", picture.size, "white")
        picture = Image.alpha_composite(background, picture)
    aspect = picture.height / picture.width
    width = min(width, height / aspect)
    height = width * aspect

    # Sample at half the line spacing; finer detail can't be drawn anyway.
    columns = max(2, math.ceil(width / (spacing / 2)))
    rows = max(2, math.ceil(height / (spacing / 2)))
    darkness = 1 - np.asarray(picture.convert("L").resize((columns, rows), Image.LANCZOS), float) / 255

    corners = np.array([0, width, width + 1j * height, 1j * height])
    paths: Paths = []
    for angle, threshold in ((0, 0.2), (90, 0.4), (45, 0.6), (-45, 0.8)):
        along = np.exp(1j * math.radians(angle))
        across = along * 1j
        offsets = (corners * across.conjugate()).real
        reach = (corners * along.conjugate()).real
        t = np.arange(reach.min(), reach.max() + spacing / 2, spacing / 2)
        for k, offset in enumerate(np.arange(offsets.min() + spacing / 2, offsets.max(), spacing)):
            points = offset * across + t * along
            inside = (points.real >= 0) & (points.real < width) & (points.imag >= 0) & (points.imag < height)
            column = np.clip((points.real / width * columns).astype(int), 0, columns - 1)
            row = np.clip(((height - points.imag) / height * rows).astype(int), 0, rows - 1)
            dark = inside & (darkness[row, column] > threshold)
            for run in _runs(dark):
                segment = np.array([points[run[0]], points[run[-1]]])
                if abs(segment[1] - segment[0]) >= spacing:
                    paths.append(segment if k % 2 == 0 else segment[::-1])
    return paths


def _runs(mask: np.ndarray) -> list[np.ndarray]:
    """Index arrays of each stretch of consecutive True values."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(np.int8), [0]])))
    return [np.arange(start, end) for start, end in zip(edges[::2], edges[1::2])]


# MARK: - Built in


def test_pattern(config: Config) -> Drawing:
    """Shapes for checking the plotter: square with diagonals (squareness, straight
    lines), circle (both axes moving together), star (sharp corners), fan (straight
    lines at every angle) and text, shrunk to fit if needed."""
    paths: Paths = []

    side = 60
    paths.append(geometry.polygon([0, side, side + side * 1j, side * 1j]))
    paths.append(np.array([0, side + side * 1j]))
    paths.append(np.array([side, side * 1j]))

    paths.append(geometry.circle(complex(110, 30), 30))

    center, outer, inner = complex(190, 30), 32, 13
    paths.append(geometry.polygon([
        center + (outer if i % 2 == 0 else inner) * np.exp(1j * (math.pi / 2 + i * math.pi / 5))
        for i in range(10)
    ]))

    hub = complex(30, -15)
    for i in range(13):
        direction = np.exp(-1j * math.pi * i / 12)
        paths.append(np.array([hub + 5 * direction, hub + 45 * direction]))

    paths += geometry.translate(fonts.text("hi-plotter 0123456789", size=10), complex(90, -25))

    drawing = Drawing(geometry.fit(paths, config.printable, grow=False), "test", "Test pattern")
    return drawing
