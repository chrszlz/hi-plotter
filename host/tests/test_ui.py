import base64

import pytest

from hiplot import sources
from hiplot.config import Config
from hiplot.ui import Studio


@pytest.fixture
def studio():
    return Studio(Config(), sim_mode=True)


def test_preview_text_in_a_system_font(studio):
    result = studio.preview({"text": "Hi", "font": "Helvetica", "size": "20", "fill": True})
    assert result["svg"].startswith("<svg")
    assert "Text:" in result["summary"]


def test_preview_an_uploaded_file_on_other_paper(studio):
    gcode = b"G21\nG0 X10 Y10\nG1 X60 Y10\nG1 X60 Y40\n"
    upload = {"name": "lines.gcode", "data": base64.b64encode(gcode).decode()}
    result = studio.preview({"file": upload, "paper": "a5-portrait"})
    assert 'viewBox="0 0 148.0 210.0"' in result["svg"]
    assert "lines.gcode: 1 strokes" in result["summary"]


def test_empty_text_asks_for_input(studio):
    with pytest.raises(sources.SourceError, match="Type some text"):
        studio.preview({"text": "  "})


def test_plot_anything_means_draw():
    from hiplot.cli import _with_default_command

    assert _with_default_command(["Hello"]) == ["draw", "Hello"]
    assert _with_default_command(["--sim", "--paper", "a5", "x.svg"]) == ["--sim", "--paper", "a5", "draw", "x.svg"]
    assert _with_default_command(["--dry-run", "--rotate", "90", "Hi"]) == ["--dry-run", "draw", "--rotate", "90", "Hi"]
    assert _with_default_command(["--sim", "test"]) == ["--sim", "test"]
    assert _with_default_command(["--help"]) == ["--help"]


def test_preview_the_built_in_sheets(studio):
    assert "Tuning sheet" in studio.preview({"builtin": "tune"})["summary"]
    assert "Test pattern" in studio.preview({"builtin": "test", "paper": "a5"})["summary"]
