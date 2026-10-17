"""Plotter settings, read from plotter.toml at the repo root."""

import re
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "plotter.toml"

DAC_MAX = 4095

# Paper sizes in mm, landscape (long side along X, parallel to the knob panel).
# "max" is the whole 15 x 10 inch bed.
PAPERS = {
    "letter": (279.4, 215.9),
    "a4": (297.0, 210.0),
    "a5": (210.0, 148.0),
    "half-letter": (215.9, 139.7),
    "max": (381.0, 254.0),
}


@dataclass
class Config:
    port: str = ""
    baud: int = 115200

    origin_x: float = 694
    origin_y: float = 948
    counts_per_mm_x: float = 7.874
    counts_per_mm_y: float = 7.874

    paper_width: float = 279.4
    paper_height: float = 215.9
    margin: float = 10.0

    draw_speed: float = 50.0
    travel_speed: float = 150.0
    accel: float = 1000.0
    cornering: float = 0.05
    sample_ms: int = 15

    pen_down_ms: int = 150
    pen_up_ms: int = 100
    settle_ms: int = 60

    path: Path = DEFAULT_PATH

    # MARK: - Coordinates

    def to_counts(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Paper millimeters to DAC counts."""
        return (
            round(self.origin_x + x_mm * self.counts_per_mm_x),
            round(self.origin_y + y_mm * self.counts_per_mm_y),
        )

    def to_mm(self, x_counts: float, y_counts: float) -> tuple[float, float]:
        """DAC counts to paper millimeters."""
        return (
            (x_counts - self.origin_x) / self.counts_per_mm_x,
            (y_counts - self.origin_y) / self.counts_per_mm_y,
        )

    def rescaled(self, counts_per_mm_x: float | None = None, counts_per_mm_y: float | None = None) -> dict:
        """Settings for a new scale that keep the paper centered where it is (under the
        boot park position), for `save(**...)`."""
        new_x = counts_per_mm_x or self.counts_per_mm_x
        new_y = counts_per_mm_y or self.counts_per_mm_y
        center_x = self.origin_x + self.paper_width / 2 * self.counts_per_mm_x
        center_y = self.origin_y + self.paper_height / 2 * self.counts_per_mm_y
        return {
            "counts_per_mm_x": round(new_x, 4),
            "counts_per_mm_y": round(new_y, 4),
            "origin_x": round(center_x - self.paper_width / 2 * new_x),
            "origin_y": round(center_y - self.paper_height / 2 * new_y),
        }

    @property
    def printable(self) -> tuple[float, float, float, float]:
        """The drawable area inside the margin: (x0, y0, x1, y1) in mm."""
        m = self.margin
        return (m, m, self.paper_width - m, self.paper_height - m)

    def with_paper(self, spec: str) -> "Config":
        """A copy for another paper size, centered where the current paper's center is.
        `spec` is a name (letter, a4, a5, half-letter, max; add "-portrait" to turn it)
        or a size like "200x150" (mm) or "8x6in"."""
        name = spec.lower().strip()
        portrait = name.endswith("-portrait")
        name = name.removesuffix("-portrait")
        if name in PAPERS:
            width, height = PAPERS[name]
        else:
            match = re.fullmatch(r"([\d.]+)\s*x\s*([\d.]+)\s*(mm|in)?", name)
            if not match:
                raise ValueError(f"Unknown paper {spec!r}: use {', '.join(PAPERS)} or a size like 200x150")
            factor = 25.4 if match.group(3) == "in" else 1.0
            width, height = float(match.group(1)) * factor, float(match.group(2)) * factor
        if portrait:
            width, height = height, width

        center = self.to_counts(self.paper_width / 2, self.paper_height / 2)
        return replace(
            self,
            paper_width=width,
            paper_height=height,
            origin_x=center[0] - width / 2 * self.counts_per_mm_x,
            origin_y=center[1] - height / 2 * self.counts_per_mm_y,
        )

    # MARK: - Saving

    def save(self, **changes):
        """Sets attributes and writes them into plotter.toml, keeping its comments."""
        text = self.path.read_text() if self.path.exists() else ""
        for name, value in changes.items():
            setattr(self, name, value)
            section, key = _KEYS[name]
            text = _set_toml_value(text, section, key, value)
        self.path.write_text(text)


# Config attribute -> (toml section, toml key).
_KEYS = {
    "port": ("serial", "port"),
    "baud": ("serial", "baud"),
    "origin_x": ("calibration", "origin_x"),
    "origin_y": ("calibration", "origin_y"),
    "counts_per_mm_x": ("calibration", "counts_per_mm_x"),
    "counts_per_mm_y": ("calibration", "counts_per_mm_y"),
    "paper_width": ("paper", "width"),
    "paper_height": ("paper", "height"),
    "margin": ("paper", "margin"),
    "draw_speed": ("motion", "draw_speed"),
    "travel_speed": ("motion", "travel_speed"),
    "accel": ("motion", "accel"),
    "cornering": ("motion", "cornering"),
    "sample_ms": ("motion", "sample_ms"),
    "pen_down_ms": ("pen", "down_ms"),
    "pen_up_ms": ("pen", "up_ms"),
    "settle_ms": ("pen", "settle_ms"),
}


def load(path: Path = DEFAULT_PATH) -> Config:
    config = Config(path=path)
    if not path.exists():
        return config

    data = tomllib.loads(path.read_text())
    types = {f.name: f.type for f in fields(Config)}
    for name, (section, key) in _KEYS.items():
        if key in data.get(section, {}):
            value = data[section][key]
            setattr(config, name, int(value) if types[name] is int else value)
    return config


def _format(value) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".") if value != int(value) else f"{value:.1f}"
    return str(value)


def _set_toml_value(text: str, section: str, key: str, value) -> str:
    """Replaces `key = ...` inside [section], keeping any trailing comment."""
    lines = text.splitlines()
    current = None
    section_end = None
    for i, line in enumerate(lines):
        header = re.match(r"\s*\[([^\]]+)\]", line)
        if header:
            if current == section:
                section_end = i
            current = header.group(1).strip()
            continue
        if current != section:
            continue
        match = re.match(rf"(\s*{re.escape(key)}\s*=\s*)([^#]*?)(\s*#.*)?$", line)
        if match:
            lines[i] = match.group(1) + _format(value) + (match.group(3) or "")
            return "\n".join(lines) + "\n"

    if current == section:
        section_end = len(lines)
    if section_end is None:
        lines += ["", f"[{section}]"]
        section_end = len(lines)
    lines.insert(section_end, f"{key} = {_format(value)}")
    return "\n".join(lines) + "\n"
