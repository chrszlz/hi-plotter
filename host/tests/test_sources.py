import io

import numpy as np
import pytest
from PIL import Image

from hiplot import fonts, geometry, sources
from hiplot.config import Config


@pytest.fixture
def config():
    return Config()


def lengths(paths):
    return sorted(round(float(np.abs(np.diff(p)).sum()), 1) for p in paths)


# MARK: - Text and fonts


def test_plain_text_is_placed_at_the_top_left(config):
    drawing = sources.load("Hello", config)
    x0, y0, x1, y1 = config.printable
    bx0, _, _, by1 = geometry.bounds(drawing.paths)
    assert drawing.kind == "text"
    assert bx0 == pytest.approx(x0, abs=2)
    assert by1 == pytest.approx(y1, abs=0.5)


def test_missing_file_is_an_error_not_text(config):
    with pytest.raises(sources.SourceError, match="No such file"):
        sources.load("nope/drawing.svg", config)


def test_system_fonts_are_found_by_loose_name():
    assert fonts.find("futural") == "futural"
    helvetica = fonts.find("helvetica bold")
    assert helvetica.name.lower() == "helvetica bold"
    with pytest.raises(fonts.FontNotFound, match="Did you mean"):
        fonts.find("helvetca")


def test_outline_font_text_has_closed_letter_shapes():
    paths = fonts.text("O", size=20, font="Helvetica")
    assert len(paths) == 2  # outside and inside of the O
    assert all(abs(p[0] - p[-1]) < 1e-6 for p in paths)
    x0, y0, x1, y1 = geometry.bounds(paths)
    assert y1 == pytest.approx(0, abs=0.8)  # capital top at y = 0
    assert 12 < y1 - y0 < 16  # cap height ~ 0.7 x size


def test_fill_hatches_inside_the_letter_only():
    outline = fonts.text("O", size=20, font="Helvetica")
    filled = fonts.text("O", size=20, font="Helvetica", fill=1.0)
    hatch = filled[len(outline):]
    assert hatch
    center = np.mean(np.concatenate(outline))
    # No hatch line passes through the hole in the middle of the O.
    for line in hatch:
        t = np.linspace(0, 1, 50)
        points = line[0] + (line[1] - line[0]) * t
        assert np.min(np.abs(points - center)) > 2


def test_sizes_with_units():
    assert fonts.parse_size("12") == 12
    assert fonts.parse_size("1in") == 25.4
    assert fonts.parse_size("72pt") == pytest.approx(25.4)
    assert fonts.parse_size("1.5cm") == 15


# MARK: - File formats


def test_svg_is_fitted_to_the_page(config):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 20 10">' \
          b'<path d="M0 0 L20 10" stroke="black"/></svg>'
    drawing = sources.load_bytes(svg, "line.svg", config)
    x0, y0, x1, y1 = geometry.bounds(drawing.paths)
    px0, py0, px1, py1 = config.printable
    assert x1 - x0 == pytest.approx(px1 - px0)
    # SVG y runs down: the line goes from top-left to bottom-right.
    line = drawing.paths[0]
    assert line[0].imag > line[-1].imag


def test_svg_keeps_its_size_with_no_fit(config):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="50mm" viewBox="0 0 50 50">' \
          b'<path d="M10 10 L40 10" stroke="black"/></svg>'
    drawing = sources.load_bytes(svg, "line.svg", config, layout=sources.Layout(fit=False))
    assert lengths(drawing.paths) == [30.0]
    # 10 mm below the paper's top edge.
    assert drawing.paths[0][0].imag == pytest.approx(config.paper_height - 10)


def test_gcode_in_inches_with_z_and_arcs():
    paths = sources.gcode(
        "G20 G90\nG0 Z0.1\nG0 X1 Y1\nG1 Z-0.1\nG1 X2 Y1 F100\nG0 Z0.1\n"
        "G0 X3 Y1\nG1 Z-0.1\nG2 X3 Y1 I0.5 J0 (circle)\nG0 Z1\n"
    )
    assert len(paths) == 2
    assert paths[0][0] == pytest.approx(25.4 + 25.4j)
    assert paths[0][-1] == pytest.approx(50.8 + 25.4j)
    radius = np.abs(paths[1] - (3.5 * 25.4 + 25.4j))
    assert radius == pytest.approx(12.7, abs=0.01)


def test_gcode_without_pen_commands_draws_on_g1():
    paths = sources.gcode("G21\nG0 X0 Y0\nG1 X10\nG1 Y10\nG0 X20 Y20\nG1 X30\n")
    assert lengths(paths) == [10.0, 20.0]


def test_hpgl_absolute_and_relative():
    paths = sources.hpgl("IN;SP1;PU400,400;PD800,400,800,800;PU;PR;PU400,0;PD0,400;PU;")
    assert len(paths) == 2
    assert paths[0].tolist() == [10 + 10j, 20 + 10j, 20 + 20j]
    assert paths[1].tolist() == [30 + 20j, 30 + 30j]


def test_image_dark_areas_get_more_lines(config):
    picture = Image.new("L", (200, 100), 255)
    picture.paste(0, (0, 0, 100, 100))  # left half black, right half white
    buffer = io.BytesIO()
    picture.save(buffer, "PNG")
    drawing = sources.load_bytes(buffer.getvalue(), "half.png", config)
    x0, _, x1, _ = geometry.bounds(drawing.paths)
    px0, _, px1, _ = config.printable
    # The picture is fitted to the printable width; only its black half gets lines.
    assert x1 - x0 == pytest.approx((px1 - px0) / 2, abs=2)


def test_drawings_too_big_are_shrunk_with_a_note(config):
    drawing = sources.load_bytes(b"G21\nG1 X0 Y0\nG1 X1000 Y0\n", "wide.gcode", config)
    assert geometry.inside(drawing.paths, (0, 0, config.paper_width, config.paper_height))
    assert drawing.notes


def test_paper_sizes_stay_centered(config):
    a5 = config.with_paper("a5")
    assert (a5.paper_width, a5.paper_height) == (210, 148)
    center = config.to_counts(config.paper_width / 2, config.paper_height / 2)
    assert a5.to_counts(105, 74) == center
    portrait = config.with_paper("150x100-portrait")
    assert (portrait.paper_width, portrait.paper_height) == (100, 150)


def test_text_mentioning_a_file_is_still_text(config):
    assert sources.load("see notes.txt", config).kind == "text"
    assert not sources.is_file_name("Read the README.md")
    assert sources.is_file_name("drawing.svg")


def test_gcode_without_spaces():
    paths = sources.gcode("G21G90\nG0Z5\nG0X0Y0\nG1Z-1\nG1X10Y0\nG0Z5\nG0X20\n")
    assert lengths(paths) == [10.0]


def test_rotated_image_is_centered_and_fits(config):
    picture = Image.new("L", (300, 100), 0)  # wide black picture
    buffer = io.BytesIO()
    picture.save(buffer, "PNG")
    drawing = sources.load_bytes(buffer.getvalue(), "wide.png", config, layout=sources.Layout(rotate=90))
    x0, y0, x1, y1 = geometry.bounds(drawing.paths)
    assert not drawing.notes  # made to fit, not shrunk after the fact
    assert y1 - y0 > x1 - x0  # tall now
    assert (x0 + x1) / 2 == pytest.approx(config.paper_width / 2, abs=1)
    assert (y0 + y1) / 2 == pytest.approx(config.paper_height / 2, abs=1)


def test_single_stroke_fonts_get_plain_text_and_notes_for_the_rest(config):
    assert fonts.prepare("café “quoted” — ok", "futural") == 'cafe "quoted" - ok'
    assert fonts.missing("café 日本", "futural") == "日本"
    drawing = sources.load("naïve 日本", config)
    assert any("日本" in note for note in drawing.notes)
    assert fonts.missing("café", "Helvetica") == ""


def test_line_drawings_are_traced_down_their_middle(config):
    from PIL import ImageDraw

    from hiplot import lineart

    picture = Image.new("L", (400, 300), 255)
    draw = ImageDraw.Draw(picture)
    draw.line([(50, 150), (350, 150)], fill=0, width=7)    # a thick horizontal line
    draw.ellipse([150, 30, 250, 130], outline=0, width=5)  # a ring
    buffer = io.BytesIO()
    picture.save(buffer, "PNG")
    data = buffer.getvalue()

    assert lineart.is_line_art(lineart.grayscale(data))
    paths = lineart.trace(data, 400, 300)  # 1 mm per pixel
    lengths_mm = sorted(float(np.abs(np.diff(p)).sum()) for p in paths)
    # One stroke along the line's middle (y = 150 from the top), one loop for the ring.
    assert len(paths) == 2
    line = min(paths, key=lambda p: np.ptp(p.imag))
    assert np.ptp(line.real) == pytest.approx(300, abs=8)
    assert np.mean(line.imag) == pytest.approx(150, abs=1.5)
    assert lengths_mm[1] == pytest.approx(np.pi * 95, rel=0.08)


def test_photos_are_hatched_not_traced(config):
    from hiplot import lineart

    gradient = Image.fromarray(np.tile(np.linspace(0, 255, 200, dtype=np.uint8), (100, 1)))
    buffer = io.BytesIO()
    gradient.save(buffer, "PNG")
    assert not lineart.is_line_art(lineart.grayscale(buffer.getvalue()))
