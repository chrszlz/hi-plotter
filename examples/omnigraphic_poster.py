"""A full-plate poster of the setup: a technical line drawing of the Omnigraphic 2000's
front, and a simplified wiring diagram of the Arduino circuit that drives it.

    uv run python examples/omnigraphic_poster.py --preview poster.png   # look first
    uv run python examples/omnigraphic_poster.py --plot                 # then draw it

It fills the whole 15 x 10 inch plate (paper covering the bed), using the plate's
corner from the 2020 calibration rather than the letter-sized paper in plotter.toml.
"""

import argparse
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from hiplot import fonts, geometry, jobs, preview
from hiplot.config import load
from hiplot.device import Plotter
from hiplot.sources import Drawing

# The plate's lower-left corner (ruler 0, 0) in DAC counts, from the 2020 sketch.
PLATE_ORIGIN = (694, 948)
PLATE = (381.0, 254.0)  # 15 x 10 in
MARGIN = 15.0
FONT = "futural"  # single-stroke sans: the closest a pen gets to Helvetica


class Sheet:
    """Strokes in paper mm (origin lower-left, y up)."""

    def __init__(self):
        self.paths: list[np.ndarray] = []

    def add(self, points):
        points = np.asarray(points, dtype=complex)
        if len(points) > 1:
            self.paths.append(points)

    def text(self, content: str, at: complex, size: float, align: str = "left", middle: bool = False,
             turn: int = 0):
        """Text with its top-left (or top-center / top-right) at `at`; with middle=True the
        capitals are centered on `at` vertically."""
        strokes = fonts.text(content, size, FONT, align=align)
        if middle:
            strokes = geometry.translate(strokes, 1j * size * 0.33)
        strokes = geometry.rotate(strokes, turn)
        for stroke in strokes:
            self.add(stroke + at)


# MARK: - Shapes


def rect(a: complex, b: complex) -> list[complex]:
    return [a, complex(b.real, a.imag), b, complex(a.real, b.imag), a]


def rounded(a: complex, b: complex, r: float) -> list[complex]:
    x0, y0, x1, y1 = min(a.real, b.real), min(a.imag, b.imag), max(a.real, b.real), max(a.imag, b.imag)
    points = []
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(7):
            angle = math.radians(start + 15 * k)
            points.append(complex(cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points + points[:1]


def circle(center: complex, r: float) -> np.ndarray:
    count = max(12, min(72, int(2 * math.pi * r / 0.6)))
    return center + r * np.exp(1j * np.linspace(0, 2 * math.pi, count + 1))


def arrowhead(tip: complex, direction: complex, length: float = 2.2) -> list[complex]:
    back = -direction / abs(direction) * length
    return [tip + back * np.exp(0.42j), tip, tip + back * np.exp(-0.42j)]


# MARK: - The recorder


def recorder(sheet: Sheet, origin: complex, s: float):
    """Front view, drawn in inches (y up from the bottom of the case) and scaled by `s`
    mm per inch."""

    def p(x, y=None):
        return origin + (x if y is None else complex(x, y)) * s

    def box(x0, y0, x1, y1, r=0.0):
        sheet.add([p(q) for q in (rounded(complex(x0, y0), complex(x1, y1), r) if r else
                                   rect(complex(x0, y0), complex(x1, y1)))])

    def ring(x, y, r_mm):
        sheet.add(circle(p(x, y), r_mm))

    def line(*points):
        sheet.add([p(q) for q in points])

    # Case, plate frame, plate.
    box(0, 0, 18.6, 15.7, 0.15)
    box(1.6, 3.6, 18.2, 14.35)
    box(2.5, 3.8, 17.9, 14.15)

    # X ruler along the top: 0-15 in.
    box(2.2, 14.45, 18.1, 15.35)
    for i in range(16):
        x = 2.7 + i
        line(complex(x, 14.45), complex(x, 14.78))
        if i < 15:
            line(complex(x + 0.5, 14.45), complex(x + 0.5, 14.62))
        sheet.text(str(i), p(x, 15.24), 0.32 * s, align="center")

    # The arm (Y axis), with its 0-10 in ruler, at X = 0.
    box(2.38, 3.72, 3.02, 14.42)
    for j in range(11):
        y = 4.0 + j
        line(complex(2.74, y), complex(3.02, y))
        if j < 10:
            line(complex(2.88, y + 0.5), complex(3.02, y + 0.5))
        sheet.text(str(j), p(2.56, y), 0.22 * s, align="center", middle=True)
    line(complex(2.55, 14.42), complex(2.85, 14.42), complex(2.7, 14.2), complex(2.55, 14.42))

    # Pen carriage on the arm, at Y = 1 in.
    box(2.2, 4.65, 3.2, 5.35, 0.06)
    box(3.2, 4.86, 3.5, 5.14)
    line(complex(3.5, 4.93), complex(3.66, 5.0), complex(3.5, 5.07))

    # Vacuum plate: slots along the edges, and clusters of holes.
    for k in range(9):
        x = 3.9 + 1.6 * k
        box(x, 13.74, x + 0.5, 13.92, 0.08)
    for k in range(8):
        x = 4.5 + 1.6 * k
        box(x, 3.98, x + 0.5, 4.16, 0.08)
    for k in range(8):
        y = 4.7 + 1.15 * k
        box(17.48, y, 17.66, y + 0.5, 0.08)
    for cx, cy in ((4.2, 12.9), (15.9, 12.9), (10.2, 8.9), (15.7, 5.0), (4.6, 4.75)):
        for a in range(4):
            for b in range(4):
                ring(cx + (a - 1.5) * 0.13, cy + (b - 1.5) * 0.13, 0.35)
    for x, y in ((6.6, 12.9), (9.2, 12.9), (12.4, 12.9), (6.3, 10.4), (9.4, 10.8), (12.7, 10.3),
                 (14.6, 11.0), (6.4, 7.2), (13.9, 7.4), (8.2, 5.3), (11.2, 5.1), (13.3, 5.8)):
        ring(x, y, 0.35)

    # Name strip and control panel.
    box(0.5, 3.05, 18.1, 3.45)
    sheet.text("2000 RECORDER", p(17.85, 3.25), 0.26 * s, align="right", middle=True)
    box(0.5, 0.4, 18.1, 2.9, 0.1)
    for x0, x1 in ((0.75, 7.75), (10.85, 17.85)):
        input_module(sheet, p, x0)
        box(x0, 0.6, x1, 2.7, 0.08)
    box(8.0, 0.6, 10.6, 2.7, 0.08)
    sheet.text("X", p(8.35, 1.65), 0.5 * s, align="center", middle=True)
    sheet.text("Y", p(10.25, 1.65), 0.5 * s, align="center", middle=True)
    box(8.75, 1.75, 9.85, 2.45, 0.04)
    box(8.9, 1.88, 9.7, 2.32)
    box(8.75, 0.8, 9.85, 1.5, 0.04)

    # Dimensions: 15 in across, 10 in up.
    top = 16.0
    for x in (2.7, 17.7):
        line(complex(x, 15.45), complex(x, top + 0.15))
    line(complex(2.7, top), complex(17.7, top))
    sheet.add(arrowhead(p(2.7, top), -1))
    sheet.add(arrowhead(p(17.7, top), 1))
    sheet.text("15 IN", p(10.2, top + 0.55), 0.3 * s, align="center")
    left = -0.55
    for y in (4.0, 14.0):
        line(complex(-0.1, y), complex(left - 0.15, y))
    line(complex(left, 4.0), complex(left, 14.0))
    sheet.add(arrowhead(p(left, 4.0), -1j))
    sheet.add(arrowhead(p(left, 14.0), 1j))
    sheet.text("10 IN", p(left - 0.2, 9.0), 0.3 * s, align="center", turn=90)

    # Callouts under the panel.
    for x, y, label in ((1.6, 1.2, "X IN"), (9.3, 0.8, "PEN"), (11.7, 1.2, "Y IN")):
        line(complex(x, y), complex(x, -0.45))
        sheet.text(label, p(x, -0.6), 0.26 * s, align="center")


def input_module(sheet: Sheet, p, ox: float):
    """One input: binding posts, IN/CM toggle, range knob with its scale, CAL/VAR knob
    with the vernier inside, and the zero knob."""
    s = abs(p(1) - p(0))

    def ring(x, y, r):
        sheet.add(circle(p(ox + x, y), r * s))

    for x, y in ((0.5, 2.05), (1.15, 2.05), (0.5, 1.2), (1.15, 1.2)):
        ring(x, y, 0.24)
        ring(x, y, 0.1)

    ring(2.1, 1.6, 0.17)
    sheet.add([p(ox + 2.1, 1.6), p(ox + 2.1, 2.08)])
    ring(2.1, 2.12, 0.05)

    center = complex(ox + 3.55, 1.65)
    ring(3.55, 1.65, 0.6)
    ring(3.55, 1.65, 0.45)
    pointer = np.exp(1j * math.radians(200))
    sheet.add([p(center + 0.2 * pointer), p(center + 0.45 * pointer)])
    for k in range(9):
        angle = np.exp(1j * math.radians(225 - k * 33.75))
        sheet.add([p(center + 0.68 * angle), p(center + 0.8 * angle)])

    center = complex(ox + 5.1, 1.65)
    ring(5.1, 1.65, 0.42)
    ring(5.1, 1.65, 0.17)
    pointer = np.exp(1j * math.radians(-60))
    sheet.add([p(center + 0.17 * pointer), p(center + 0.42 * pointer)])

    ring(6.35, 1.65, 0.4)
    ring(6.35, 1.65, 0.3)
    ring(6.35, 1.83, 0.05)


# MARK: - Wiring


def wiring(sheet: Sheet, origin: complex, k: float):
    """The circuit, laid out in mm with y going down from `origin` and scaled by k."""

    def p(x, y):
        return origin + complex(x, -y) * k

    def wire(*points):
        sheet.add([p(*q) for q in points])

    def box(x0, y0, x1, y1, r=1.6):
        sheet.add([origin + complex(q.real, -q.imag) * k for q in rounded(complex(x0, y0), complex(x1, y1), r)])

    def dot(x, y):
        sheet.add(circle(p(x, y), 0.7 * k))
        sheet.add(circle(p(x, y), 0.3 * k))

    def label(content, x, y, size=3.0, align="left"):
        sheet.text(content, p(x, y), size * k, align=align, middle=True)

    # Mac, over USB.
    sheet.add([origin + complex(q.real, -q.imag) * k for q in rounded(8 + 6j, 42 + 28j, 1.5)])
    box(10.5, 8.5, 39.5, 25.5, 0.6)
    wire((2, 29), (48, 29), (50, 32), (0, 32), (2, 29))
    label("MAC", 25, 36, 3.2, "center")
    wire((25, 39.5), (25, 55))
    label("USB", 28, 47)

    # Arduino Uno.
    box(5, 55, 50, 119)
    label("ARDUINO UNO", 9, 60, 3.4)
    pins = {"D13": 66, "D11": 74, "D10": 82, "5V": 97, "GND": 105, "D9": 113}
    for name, y in pins.items():
        label(name, 47.5, y, 3.0, "right")

    # MCP4822 DAC.
    box(72, 57, 102, 89)
    label("MCP4822", 87, 61, 3.0, "center")
    for name, y in (("SCK", 66), ("SDI", 74), ("CS", 82)):
        label(name, 74.5, y, 2.6)
    label("OUT A", 99.5, 66, 2.6, "right")
    label("OUT B", 99.5, 78, 2.6, "right")
    label("VDD", 80, 85.5, 2.4, "center")
    label("GND", 94, 85.5, 2.4, "center")
    for y in (66, 74, 82):
        wire((50, y), (72, y))
    label("SPI", 61, 61, 2.8, "center")

    # Power to the DAC; ground shared with the recorder.
    wire((50, 97), (80, 97), (80, 89))
    wire((50, 105), (94, 105), (94, 89))
    wire((94, 105), (94, 141))
    dot(94, 105)

    # Analog outputs to the X and Y inputs.
    wire((102, 66), (112, 66), (112, 141))
    wire((102, 78), (106, 78), (106, 141))
    label("0-4 V", 103.5, 60, 2.8)

    # D9 drives the relay coil, with a flyback diode across it.
    wire((50, 113), (60, 113), (60, 123))
    box(56, 123, 64, 134, 0.6)
    wire((60, 134), (60, 143))
    wire((55, 143), (65, 143))
    wire((57, 145), (63, 145))
    wire((59, 147), (61, 147))
    wire((60, 118), (50, 118), (50, 125))
    wire((47, 131), (53, 131), (50, 126), (47, 131))
    wire((47, 126), (53, 126))
    wire((50, 131), (50, 138), (60, 138))
    dot(60, 118)
    dot(60, 138)
    label("RELAY", 60, 151, 2.8, "center")

    # Relay contacts switch the recorder's pen lift.
    sheet.add(circle(p(74, 130), 0.8 * k))
    sheet.add(circle(p(82, 130), 0.8 * k))
    wire((74.6, 129.4), (81.2, 125.2))
    for x in np.arange(64.6, 77.6, 2.2):
        wire((x, 128.6), (min(x + 1.2, 77.4), 128.6 - 0.25 * (min(x + 1.2, 77.4) - x)))
    wire((74, 130.8), (74, 141))
    wire((82, 130.8), (82, 141))

    # The recorder's terminals.
    box(68, 141, 118, 166)
    for x, name in ((74, "PEN"), (82, "COM"), (94, "GND"), (106, "Y+"), (112, "X+")):
        sheet.add(circle(p(x, 141), 0.8 * k))
        label(name, x, 146, 2.4, "center")
    label("RECORDER", 93, 157, 3.4, "center")


# MARK: - Poster


def poster() -> list[np.ndarray]:
    sheet = Sheet()
    width, height = PLATE
    top = height - MARGIN

    sheet.text("HOUSTON INSTRUMENT OMNIGRAPHIC 2000", complex(MARGIN, top), 7.0)
    sheet.text("X-Y RECORDER, DRIVEN AS A PEN PLOTTER", complex(MARGIN, top - 9.5), 3.6)

    scale = 11.5  # mm per inch of the recorder
    base = complex(MARGIN + 11, MARGIN + 13)
    recorder(sheet, origin=base, s=scale)

    # The wiring diagram lines up with the top of the recorder's case.
    case_top = base.imag + 15.7 * scale
    column = base.real + 18.6 * scale + 14
    k = (width - MARGIN - column) / 119
    sheet.text("WIRING", complex(column, case_top + 9.5), 4.5)
    wiring(sheet, origin=complex(column, case_top), k=k)
    return sheet.paths


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", type=Path, help="write a .png or .svg of the plan")
    parser.add_argument("--plot", action="store_true", help="draw it on the plotter")
    args = parser.parse_args()

    config = replace(load(), paper_width=PLATE[0], paper_height=PLATE[1], origin_x=PLATE_ORIGIN[0],
                     origin_y=PLATE_ORIGIN[1], margin=MARGIN)
    paths = poster()
    if not geometry.inside(paths, (0, 0, *PLATE)):
        sys.exit(f"The poster runs off the plate: {geometry.bounds(paths)}")

    plotter = Plotter.open(config.port, config.baud) if args.plot else None
    start = jobs.position_mm(plotter, config) if plotter else 0j
    job = jobs.prepare(Drawing(paths, "poster", "Omnigraphic poster"), config, start)
    print(job.summary)
    if args.preview:
        down, up = job.preview_strokes(config)
        preview.write(args.preview, config, down, up, title="Omnigraphic poster")
        print(f"Preview: {args.preview}")
    if plotter:
        def progress(fraction, left):
            sys.stdout.write(f"\r  {fraction:4.0%}  {jobs.duration(left * 1000)} left ")
            sys.stdout.flush()
        try:
            jobs.stream(plotter, job, progress)
            print("\r  done" + " " * 30)
        except jobs.Stopped:
            jobs.rest(plotter, config)
            sys.exit("\nStopped. Pen lifted and moved to the plate corner.")


if __name__ == "__main__":
    main()
