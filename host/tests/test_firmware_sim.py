"""The real firmware, compiled for the Mac (host/sim), driven through the same
Plotter class the CLI uses."""

import shutil
import time

import pytest

from hiplot import sim
from hiplot.device import Plotter, PlotterError, SimTransport

pytestmark = pytest.mark.skipif(shutil.which("c++") is None, reason="needs a C++ compiler")


@pytest.fixture
def plotter(tmp_path):
    log = tmp_path / "sim.log"
    p = Plotter(SimTransport(sim.build(), log))
    p.log_path = log
    yield p
    p.close()


def test_boots_parked_with_the_pen_up(plotter):
    status = plotter.status()
    assert (status.x, status.y, status.pen_down, status.idle) == (2048, 2048, False, True)


def test_moves_in_a_straight_line_on_time(plotter):
    plotter.send("M 1000 1000 0")
    plotter.send("M 3000 2000 400")
    plotter.wait_idle()
    plotter.close()

    rows = sim.read_log(plotter.log_path)
    start = next(i for i, r in enumerate(rows) if r[1:3] == (1000, 1000))
    line = rows[start:]
    assert line[-1][1:3] == (3000, 2000)
    # Every point sits on the line from (1000, 1000) to (3000, 2000).
    for _, x, y, _ in line:
        assert abs((y - 1000) - (x - 1000) / 2) <= 1
    elapsed_ms = (line[-1][0] - line[0][0]) / 1000
    assert 380 <= elapsed_ms <= 450


def test_pen_commands_run_in_order(plotter):
    plotter.run(["D", "W 50", "M 2100 2048 50", "U"])
    plotter.wait_idle()
    plotter.close()
    pens = [row[3] for row in sim.read_log(plotter.log_path)]
    assert pens[0] is False and pens[-1] is False
    assert True in pens


def test_stop_clears_the_queue_and_lifts_the_pen(plotter):
    plotter.run(["D", "M 4000 4000 3000"])
    time.sleep(0.3)
    plotter.stop()
    status = plotter.status()
    assert status.idle and not status.pen_down
    assert 2048 < status.x < 4000


def test_pen_level_setting(plotter):
    assert plotter.pen_up_level() == 1
    plotter.send("P 0")
    assert plotter.pen_up_level() == 0


def test_bad_commands_are_rejected(plotter):
    with pytest.raises(PlotterError, match="unknown command"):
        plotter.send("Z 1 2")
    with pytest.raises(PlotterError, match="usage"):
        plotter.send("M 10")
    with pytest.raises(PlotterError, match="bad number"):
        plotter.send("M 1 2 3 4")
    plotter.send("M 9999 -5 0")  # clamped to the DAC range
    status = plotter.status()
    assert (status.x, status.y) == (4095, 0)


def test_counts_when_the_queue_runs_dry(plotter):
    before = plotter.status().late
    time.sleep(0.05)
    plotter.run(["M 2100 2048 100", "M 2200 2048 100", "M 2300 2048 100"])  # back to back
    plotter.wait_idle()
    assert plotter.status().late == before + 1  # only the start of the job
    time.sleep(0.05)
    plotter.send("M 2400 2048 100")  # after a gap: starts late
    plotter.wait_idle()
    assert plotter.status().late == before + 2
