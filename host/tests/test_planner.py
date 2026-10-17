import math

import numpy as np
import pytest

from hiplot import planner, preview
from hiplot.config import Config
from hiplot.planner import Profile


def config(**changes) -> Config:
    c = Config(origin_x=500, origin_y=500, counts_per_mm_x=7.874, counts_per_mm_y=7.874)
    for key, value in changes.items():
        setattr(c, key, value)
    return c


def m_commands(commands: list[str]) -> list[tuple[int, int, int]]:
    return [tuple(map(int, c.split()[1:])) for c in commands if c.startswith("M")]


# MARK: - Profile


def test_straight_line_follows_a_trapezoid():
    profile = Profile(np.array([0, 100 + 0j]), speed=50, accel=1000, cornering=0.05)
    # 0.05 s to reach 50 mm/s over 1.25 mm, both ends; the remaining 97.5 mm at 50 mm/s.
    assert profile.duration == pytest.approx(0.05 + 97.5 / 50 + 0.05)
    assert profile.position(profile.duration) == pytest.approx(100)
    assert profile.position(0.05) == pytest.approx(1.25)


def test_short_line_never_reaches_full_speed():
    profile = Profile(np.array([0, 1 + 0j]), speed=50, accel=1000, cornering=0.05)
    # Triangle profile: peak sqrt(a * L) ~= 31.6 mm/s.
    assert profile.duration == pytest.approx(2 * math.sqrt(1 / 1000))


def test_speed_and_acceleration_stay_in_limits():
    rng = np.random.default_rng(1)
    path = np.cumsum(rng.normal(size=200) + 1j * rng.normal(size=200)) * 3
    speed, accel = 50, 1000
    profile = Profile(path, speed=speed, accel=accel, cornering=0.05)
    for v0, peak, v1, *_ in profile.segments:
        assert max(v0, peak, v1) <= speed + 1e-9
    # Arc length over time shouldn't outrun the speed limit.
    times = np.linspace(0, profile.duration, 4000)
    steps = np.abs(np.diff([profile.position(t) for t in times]))
    assert steps.max() / (times[1] - times[0]) <= speed * 1.01


def test_sharp_corners_slow_down_and_get_their_own_sample():
    path = np.array([0, 50, 50 + 50j])
    profile = Profile(path, speed=50, accel=1000, cornering=0.05)
    v_corner = profile.segments[0][2]
    assert 0 < v_corner < 15  # a 90 degree corner is taken slowly, not stopped at
    samples = profile.samples(0.015)
    assert any(point == 50 for _, point in samples)


def test_reversal_stops():
    profile = Profile(np.array([0, 10, 0j]), speed=50, accel=1000, cornering=0.05)
    assert profile.segments[0][2] == 0


# MARK: - Plan


def test_plan_lifts_draws_and_lifts():
    c = config()
    job = planner.plan([np.array([10 + 10j, 60 + 10j])], c, start=0j, end=0j)
    pen = [cmd for cmd in job.commands if cmd in ("U", "D")]
    assert pen == ["U", "D", "U"]
    assert job.strokes == 1
    assert job.draw_mm == pytest.approx(50)


def test_plan_times_add_up_without_drift():
    c = config(settle_ms=0, pen_down_ms=0, pen_up_ms=0)
    path = np.array([10 + 10j, 200 + 10j])
    job = planner.plan([path], c, start=10 + 10j)
    total = sum(ms for _, _, ms in m_commands(job.commands))
    profile = Profile(path, c.draw_speed, c.accel, c.cornering)
    assert abs(total - profile.duration * 1000) <= 1


def test_plan_ends_exactly_on_target():
    c = config()
    job = planner.plan([np.array([10 + 10j, 33.3 + 71.7j])], c, start=0j)
    assert m_commands(job.commands)[-1][:2] == c.to_counts(33.3, 71.7)


def test_segments_are_long_enough_for_the_serial_link():
    c = config()
    circle = 100 + 100j + 40 * np.exp(1j * np.linspace(0, 2 * math.pi, 800))
    job = planner.plan([circle], c, start=100 + 100j)
    durations = [ms for _, _, ms in m_commands(job.commands)]
    assert np.mean(durations) >= 10


def test_off_scale_drawing_is_refused():
    c = config()
    with pytest.raises(planner.OutOfRange):
        planner.plan([np.array([0j, 1000 + 0j])], c, start=0j)


def test_preview_replays_strokes():
    c = config()
    paths = [np.array([10 + 10j, 20 + 10j]), np.array([30 + 10j, 40 + 10j])]
    job = planner.plan(paths, c, start=0j, end=0j)
    down, up = preview.from_commands(job.commands, c, c.to_counts(0, 0))
    drawn = [s for s in down if len(s) > 1]
    assert len(drawn) == 2
    assert drawn[0][-1] == pytest.approx(20 + 10j, abs=0.1)


def test_tuning_sheet_uses_each_sections_settings():
    from hiplot import geometry, tuning

    c = config(origin_x=948, origin_y=1198)
    job = tuning.job(c)
    assert geometry.inside(job.drawing.paths, c.printable)
    waits = {int(cmd.split()[1]) for cmd in job.plan.commands if cmd.startswith("W")}
    assert set(tuning.PEN_MS) <= waits  # every pen timing is used
    assert job.elapsed_ms[-1] == job.plan.duration_ms


def test_dance_stays_on_the_paper_with_the_pen_up_while_moving():
    from hiplot import dance

    c = config(origin_x=948, origin_y=1198)
    moves = dance.routine(c, start=0j)
    pen_down = False
    for _, commands, _ in moves:
        for command in commands:
            if command in ("D", "U"):
                pen_down = command == "D"
            elif command.startswith("M"):
                assert not pen_down
                x, y = c.to_mm(*map(int, command.split()[1:3]))
                assert 0 <= x <= c.paper_width and 0 <= y <= c.paper_height
