"""Draw on the Omnigraphic.

  plot "Hello, world"            write text
  plot drawing.svg               draw a file: SVG, G-code, HPGL, .txt, or an image
  plot ui                        a web page to type, preview and plot
"""

import argparse
import sys
import time
from pathlib import Path

from . import calibration, dance, fonts, geometry, guide, jog, jobs, planner, preview, sim, sources, tuning
from .config import Config, load
from .device import Plotter, PlotterError, SimTransport

SIM_TRACE = sim.ROOT / ".pio/sim/last-run.png"

COMMAND_HELP = {
    "draw": "draw text or a file (the default: `plot X` is `plot draw X`)",
    "ui": "open a web page to type text, pick fonts, drop files, preview and plot",
    "test": "draw the test pattern",
    "tune": "draw a tuning sheet to pick the best speed and pen timing for a pen",
    "dance": "a minute of choreography with the pen up, to show the plotter off",
    "fonts": "list fonts, or search them: `plot fonts avenir`",
    "setup": "guided: check restarts, set the scale from the rulers, tune speed and pen timing",
    "jog": "move the pen with the keyboard and set the paper origin",
    "pen": "pen up / down, or flip which relay level lifts it",
    "park": "lift the pen and go to the paper origin",
    "status": "position, pen state and pen setting",
    "calibrate": "draw measured lines and correct the scale",
    "send": "send raw firmware commands, e.g. 'M 2048 2048 500'",
}

# Global options, for finding where the command word goes in argv.
VALUE_OPTIONS = {"--port", "--preview", "--config", "--paper"}
GLOBAL_FLAGS = {"--sim", "--dry-run"}


def main(argv: list[str] | None = None):
    argv = _with_default_command(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(prog="plot", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sim", action="store_true",
                        help=f"use the firmware simulator instead of the plotter; draws {SIM_TRACE.name}")
    parser.add_argument("--dry-run", action="store_true", help="plan only, don't connect")
    parser.add_argument("--preview", type=Path, metavar="FILE", help="write a .png or .svg of the planned job")
    parser.add_argument("--paper", help="letter (default), a4, a5, half-letter, max, WxH in mm; "
                                        "add -portrait to turn it. Centered where the pen parks")
    parser.add_argument("--port", help="serial port (default: plotter.toml, else auto-detect)")
    parser.add_argument("--config", type=Path, help="settings file (default: plotter.toml)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    for name, help_text in COMMAND_HELP.items():
        command = commands.add_parser(name, help=help_text, description=help_text)
        ARGUMENTS.get(name, lambda c: None)(command)

    args = parser.parse_args(argv)
    config = load(args.config) if args.config else load()
    if args.port:
        config.port = args.port
    try:
        if args.paper:
            config = config.with_paper(args.paper)
        COMMANDS[args.command](args, config)
    except (PlotterError, planner.OutOfRange, sources.SourceError, ValueError) as error:
        sys.exit(f"plot: {error}")


def _with_default_command(argv: list[str]) -> list[str]:
    """`plot "Hello"` and `plot --rotate 90 file.svg` mean `plot draw ...`: the command
    goes right after the global options."""
    i = 0
    while i < len(argv):
        word = argv[i]
        if word in VALUE_OPTIONS:
            i += 2
        elif word in GLOBAL_FLAGS:
            i += 1
        else:
            return argv if word in COMMAND_HELP or word in ("-h", "--help") else argv[:i] + ["draw"] + argv[i:]
    return argv


# MARK: - Arguments


def _draw_arguments(command: argparse.ArgumentParser):
    command.add_argument("input", help='text to write, a file to draw, or "-" to read text from stdin')
    command.add_argument("--text", action="store_true", help="treat the input as text even if it looks like a file")

    text = command.add_argument_group("text")
    text.add_argument("--font", default="futural",
                      help="a single-stroke font (futural, scripts, timesr...) or any installed font "
                           "(Helvetica, 'Avenir Next Bold'...). See `plot fonts`")
    text.add_argument("--size", default="10mm", help="font size: 10mm, 0.5in, 36pt (capitals are ~0.7 of it)")
    text.add_argument("--align", choices=["left", "center", "right"], default="left")
    text.add_argument("--width", help="wrap width (default: the printable width)")
    text.add_argument("--line-spacing", type=float, default=1.4, help="in font sizes (default 1.4)")
    text.add_argument("--fill", action="store_true", help="hatch-fill outline fonts")

    _layout_arguments(command)


def _layout_arguments(command: argparse.ArgumentParser):
    layout = command.add_argument_group("layout")
    fit = layout.add_mutually_exclusive_group()
    fit.add_argument("--fit", action="store_true", default=None,
                     help="scale to fill the printable area (default for SVGs and images)")
    fit.add_argument("--no-fit", dest="fit", action="store_false",
                     help="keep the real size (default for text, G-code, HPGL)")
    layout.add_argument("--scale", type=float, default=1.0, help="multiply the size")
    layout.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="degrees counterclockwise")
    layout.add_argument("--at", type=float, nargs=2, metavar=("X", "Y"),
                        help="top-left corner in mm from the paper's lower-left corner")
    layout.add_argument("--hatch", type=float, default=0.8,
                        help="mm between hatch lines for images and --fill (default 0.8)")
    layout.add_argument("--image", choices=["auto", "lines", "hatch"], default="auto",
                        help="pictures: trace line drawings (lines) or crosshatch photos (hatch); "
                             "auto picks")


def _pen_arguments(command: argparse.ArgumentParser):
    command.add_argument("action", choices=["up", "down", "flip"])


def _fonts_arguments(command: argparse.ArgumentParser):
    command.add_argument("search", nargs="*", help="words to look for")


def _calibrate_arguments(command: argparse.ArgumentParser):
    command.add_argument("--rulers", action="store_true",
                         help="read the plotter's own rulers at two spots instead of drawing (no pen needed)")


def _dance_arguments(command: argparse.ArgumentParser):
    command.add_argument("--pen", action="store_true", help="draw the moves on the paper, pen down")


def _ui_arguments(command: argparse.ArgumentParser):
    command.add_argument("--http-port", type=int, default=8800, help="web page port (default 8800)")
    command.add_argument("--no-open", action="store_true", help="don't open the browser")


def _send_arguments(command: argparse.ArgumentParser):
    command.add_argument("lines", nargs="+")


ARGUMENTS = {
    "draw": _draw_arguments,
    "pen": _pen_arguments,
    "fonts": _fonts_arguments,
    "send": _send_arguments,
    "ui": _ui_arguments,
    "calibrate": _calibrate_arguments,
    "dance": _dance_arguments,
}


# MARK: - Connecting


def connect(args, config: Config) -> Plotter:
    def log(line: str):
        print(f"  {line}")

    if args.sim:
        return Plotter(SimTransport(sim.build(), SIM_TRACE.with_suffix(".log")), log=log)
    print("Connecting...")
    return Plotter.open(config.port, config.baud, log=log)


def finish_sim(args, config: Config, plotter: Plotter):
    """Lets the sim drain its queue, then draws what it plotted."""
    if not args.sim:
        return
    plotter.close()
    down, up = preview.from_sim_log(sim.read_log(SIM_TRACE.with_suffix(".log")), config)
    preview.write(SIM_TRACE, config, down, up)
    print(f"Simulator drawing: {SIM_TRACE}")


# MARK: - Drawing


def run_drawing(args, config: Config, drawing: sources.Drawing):
    """Plans and plots a drawing, with a preview and a progress line."""
    for note in drawing.notes:
        print(note)
    run_job(args, config, lambda start: jobs.prepare(drawing, config, start))


def run_job(args, config: Config, make_job):
    """Plots `make_job(start position in mm)`, with a preview and a progress line."""
    plotter = None if args.dry_run else connect(args, config)
    job = make_job(jobs.position_mm(plotter, config) if plotter else 0j)
    print(job.summary)

    if args.preview:
        down, up = job.preview_strokes(config)
        preview.write(args.preview, config, down, up, title=job.drawing.name)
        print(f"Preview: {args.preview}")
    if not plotter:
        return

    def progress(fraction: float, seconds_left: float):
        sys.stdout.write(f"\r  {fraction:4.0%}  {jobs.duration(seconds_left * 1000)} left ")
        sys.stdout.flush()

    try:
        jobs.stream(plotter, job, progress)
        print("\r  done" + " " * 30)
    except jobs.Stopped:
        print("\nStopped. Pen lifted.")
        sys.exit(130)
    finish_sim(args, config, plotter)


def layout_from(args) -> sources.Layout:
    return sources.Layout(
        fit=args.fit,
        scale=args.scale,
        rotate=args.rotate,
        at=complex(*args.at) if args.at else None,
        hatch=args.hatch,
        image=args.image,
    )


def cmd_draw(args, config: Config):
    style = sources.TextStyle(
        font=args.font,
        size=fonts.parse_size(args.size),
        align=args.align,
        line_spacing=args.line_spacing,
        width=fonts.parse_size(args.width) if args.width else None,
        fill=args.fill,
    )
    layout = layout_from(args)
    if args.input == "-":
        drawing = sources.text(sys.stdin.read(), config, style, layout)
    elif args.text or not sources.is_file_name(args.input):
        drawing = sources.text(args.input.replace("\\n", "\n"), config, style, layout)
    else:
        drawing = sources.load(args.input, config, style, layout)
    run_drawing(args, config, drawing)


def cmd_test(args, config: Config):
    run_drawing(args, config, sources.test_pattern(config))


def cmd_tune(args, config: Config):
    print("Tuning sheet: shapes at " + ", ".join(map(str, tuning.SPEEDS)) + " mm/s, and dashes with pen "
          "timings of " + ", ".join(map(str, tuning.PEN_MS)) + " ms. Pick the best and set them in plotter.toml.")
    run_job(args, config, lambda start: tuning.job(config, start))


def cmd_dance(args, config: Config):
    plotter = None if args.dry_run else connect(args, config)
    start = jobs.position_mm(plotter, config) if plotter else complex(config.paper_width / 2, config.paper_height / 2)
    moves = dance.routine(config, start, pen=args.pen)
    total = sum(ms for _, _, ms in moves)
    print(f"Dance{' (drawn)' if args.pen else ''}: {len([m for m in moves if m[0]])} moves, "
          f"about {jobs.duration(total)}")

    if args.preview:
        commands = [c for _, move, _ in moves for c in move]
        down, up = preview.from_commands(commands, config, config.to_counts(start.real, start.imag))
        # Dancing in the air is all pen-up, so show its path as if drawn.
        preview.write(args.preview, config, *((down, up) if args.pen else (down + up, [])), title="Dance")
        print(f"Preview: {args.preview}")
    if not plotter:
        return

    try:
        for name, commands, _ in moves:
            if name:
                print(f"  ♪ {name}")
            plotter.run(commands)
        plotter.wait_idle()
        print("  (bows)")
    except KeyboardInterrupt:
        plotter.stop()
        print("\nStopped. Pen lifted.")
        sys.exit(130)
    finish_sim(args, config, plotter)


def cmd_ui(args, config: Config):
    from . import ui

    ui.serve(config, sim_mode=args.sim, port=args.http_port, open_browser=not args.no_open)


def cmd_fonts(args, config: Config):
    words = [w.lower() for w in args.search]
    shown = 0
    for name, kind in fonts.names():
        if all(w in name.lower() for w in words):
            print(f"{name:40} {kind}")
            shown += 1
    print(f"\n{shown} fonts. Single-stroke fonts draw cleanest; outline fonts draw each letter's "
          f"edge (add --fill to hatch them in).")


# MARK: - Machine


def cmd_status(args, config: Config):
    plotter = connect(args, config)
    status = plotter.status()
    x, y = config.to_mm(status.x, status.y)
    print(f"{'idle' if status.idle else 'busy'}, pen {'down' if status.pen_down else 'up'}, "
          f"at DAC ({status.x}, {status.y}) = ({x:.1f}, {y:.1f}) mm from the paper origin")
    level = plotter.pen_up_level()
    print(f"Relay pin {'HIGH' if level else 'LOW'} lifts the pen (`plot pen flip` swaps it)")


def cmd_pen(args, config: Config):
    plotter = connect(args, config)
    if args.action == "flip":
        level = 1 - plotter.pen_up_level()
        plotter.send(f"P {level}")
        print(f"Relay pin {'HIGH' if level else 'LOW'} now lifts the pen (saved on the Arduino)")
    elif args.action == "down":
        plotter.send("D")
        print("Pen down. The firmware lifts it again after 10 s with nothing to do.")
        if not args.sim:
            time.sleep(10.5)
    else:
        plotter.send("U")
    finish_sim(args, config, plotter)


def cmd_jog(args, config: Config):
    jog.run(connect(args, config), config)


def cmd_park(args, config: Config):
    plotter = connect(args, config)
    plotter.send("U")
    plotter.run(planner.move_to(config, jobs.position_mm(plotter, config), 0j).commands)
    plotter.wait_idle()
    finish_sim(args, config, plotter)


def cmd_setup(args, config: Config):
    guide.run(config, lambda: connect(args, config), sim=args.sim)


def cmd_calibrate(args, config: Config):
    """Draws an L of known nominal size; the measured lengths give the true scale.
    With --rulers, reads the plotter's own rulers instead (no pen needed)."""
    if args.rulers:
        calibration.with_rulers(connect(args, config), config)
        return

    m = config.margin
    length_x = min(200, (config.paper_width - 2 * m) // 10 * 10)
    length_y = min(150, (config.paper_height - 2 * m) // 10 * 10)
    corner = complex(m, m)
    tick = 4
    paths = [
        geometry.polygon([corner + 1j * length_y, corner, corner + length_x], closed=False),
        geometry.polygon([corner + length_x - 1j * tick, corner + length_x + 1j * tick], closed=False),
        geometry.polygon([corner + 1j * length_y - tick, corner + 1j * length_y + tick], closed=False),
    ]
    print(f"Drawing an L: {length_x:g} mm along X and {length_y:g} mm along Y from the corner.")
    run_drawing(args, config, sources.Drawing(paths, "calibration", "Calibration"))
    if args.dry_run:
        return

    scales = {}
    for axis, nominal in (("x", length_x), ("y", length_y)):
        answer = input(f"Measured {axis.upper()} line, corner to tick, in mm (Enter to skip): ").strip()
        if not answer:
            continue
        old = getattr(config, f"counts_per_mm_{axis}")
        new = old * nominal / float(answer)
        scales[f"counts_per_mm_{axis}"] = new
        print(f"  {axis.upper()}: {old:.4f} -> {new:.4f} counts/mm ({(new / old - 1) * 100:+.2f}%)")
    if scales:
        config.save(**config.rescaled(**scales))
        print("Saved to plotter.toml. The paper stays centered where the pen parks.")


def cmd_send(args, config: Config):
    plotter = connect(args, config)
    for line in args.lines:
        for info in plotter.send(line):
            print(info)
    plotter.wait_idle()
    finish_sim(args, config, plotter)


COMMANDS = {
    "draw": cmd_draw,
    "ui": cmd_ui,
    "test": cmd_test,
    "tune": cmd_tune,
    "dance": cmd_dance,
    "fonts": cmd_fonts,
    "setup": cmd_setup,
    "jog": cmd_jog,
    "pen": cmd_pen,
    "park": cmd_park,
    "status": cmd_status,
    "calibrate": cmd_calibrate,
    "send": cmd_send,
}
