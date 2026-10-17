import numpy as np
import pytest

from hiplot import fonts, geometry, sources
from hiplot.config import Config, load


def test_optimize_joins_and_reorders_strokes():
    far = np.array([100 + 0j, 110 + 0j])
    near_backwards = np.array([20 + 0j, 10 + 0j])
    touching = np.array([20 + 0j, 30 + 0j])
    ordered = geometry.optimize([far, near_backwards, touching], start=0j)
    # The two touching strokes become one, drawn from the end nearest the start.
    assert len(ordered) == 2
    assert ordered[0][0] == 10
    assert ordered[0][-1] == 30
    assert ordered[1][0] == 100


def test_text_hangs_below_its_top_left():
    paths = fonts.text("Hello", size=10)
    x0, y0, x1, y1 = geometry.bounds(paths)
    assert y1 == pytest.approx(0, abs=0.5)  # capitals start at y = 0
    assert -10 < y0 < -5
    assert x0 >= 0


def test_text_wraps_at_width():
    one_line = geometry.bounds(fonts.text("one two three four", size=10))
    wrapped = geometry.bounds(fonts.text("one two three four", size=10, width=40))
    assert wrapped[2] <= 40
    assert wrapped[1] < one_line[1] - 10


def test_fit_centers_inside_the_box():
    square = [np.array([0, 10, 10 + 10j, 10j, 0])]
    fitted = geometry.fit(square, (0, 0, 100, 50))
    assert geometry.bounds(fitted) == pytest.approx((25, 0, 75, 50))
    assert geometry.inside(fitted, (0, 0, 100, 50))


def test_test_pattern_fits_letter_paper():
    config = Config()
    assert geometry.inside(sources.test_pattern(config).paths, config.printable)


def test_counts_and_mm_round_trip():
    c = Config(origin_x=700, origin_y=950, counts_per_mm_x=7.9, counts_per_mm_y=-7.8)
    x, y = c.to_counts(100, 50)
    assert (x, y) == (1490, 560)
    assert c.to_mm(x, y) == pytest.approx((100, 50), abs=0.1)


def test_save_keeps_comments_and_other_values(tmp_path):
    path = tmp_path / "plotter.toml"
    path.write_text(
        "[calibration]\n"
        "origin_x = 694   # counts at the corner\n"
        "origin_y = 948\n"
        "\n"
        "[paper]\n"
        "width = 279.4\n"
    )
    config = load(path)
    config.save(origin_x=1200, counts_per_mm_x=7.9, margin=12.5)

    text = path.read_text()
    assert "origin_x = 1200   # counts at the corner" in text
    assert "origin_y = 948" in text
    assert "counts_per_mm_x = 7.9" in text.split("[paper]")[0]
    assert "margin = 12.5" in text.split("[paper]")[1]

    reloaded = load(path)
    assert (reloaded.origin_x, reloaded.counts_per_mm_x, reloaded.margin) == (1200, 7.9, 12.5)


def test_rescaling_keeps_the_paper_centered():
    c = Config(origin_x=948, origin_y=1198, counts_per_mm_x=7.874, counts_per_mm_y=7.874)
    center = c.to_counts(c.paper_width / 2, c.paper_height / 2)
    changes = c.rescaled(8.0, -7.5)
    for key, value in changes.items():
        setattr(c, key, value)
    assert c.to_counts(c.paper_width / 2, c.paper_height / 2) == pytest.approx(center, abs=1)


def test_ruler_scale():
    from hiplot.calibration import RULER_POINTS, ruler_scale

    (x0, y0), (x1, y1) = RULER_POINTS
    # 200 counts per inch on X; Y's ruler counts down as the voltage rises.
    readings = [(2.0, 8.0), (2.0 + (x1 - x0) / 200, 8.0 - (y1 - y0) / 200)]
    per_mm_x, per_mm_y = ruler_scale(readings)
    assert per_mm_x == pytest.approx(200 / 25.4)
    assert per_mm_y == pytest.approx(-200 / 25.4)
