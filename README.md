# hi-plotter

Turns a Houston Instrument Omnigraphic 2000 X-Y recorder into a pen plotter that writes
text in any font and draws SVGs, G-code, HPGL and pictures.

![Houston Instrument Omnigraphic 2000 Recorder](https://cdn11.bigcommerce.com/s-a1x7hg2jgk/images/stencil/1280x1280/products/19015/106508/houston-instrument-2000-omnigraphic-recorder-1.39__82675.1490151133.jpg)

```text
Mac ── USB ──► Arduino Uno ── SPI ──► MCP4822 DAC ──► X and Y inputs (0–4.1 V)
  plot CLI       firmware       D9 ──► relay ───────► pen lift
```

The recorder is analog: each axis is a servo that moves the pen to wherever its input
voltage says. The Mac does the thinking (layout, path order, speed and acceleration) and
streams short timed straight segments; the Arduino plays them back on schedule through
the DAC. Moving smoothly instead of jumping is what keeps diagonals straight and corners
sharp — jump the voltage and each axis races on its own.

## Setup

```bash
brew install platformio uv
```

Upload the firmware (the Uno restarts, lifts the pen and parks it mid-bed):

```bash
pio run -t upload
```

`uv run` installs the Python side on first use.

## Drawing

The easiest way in is the studio page: type text, pick a font, or drop in a file, see a
preview with the time it'll take, and press Plot. Its Tests tab has the test pattern and
the tuning sheet.

```bash
uv run plot ui
```

Or from the terminal, give `plot` whatever you want drawn:

```bash
uv run plot "Hello, world"
uv run plot "Dear plotter,\nwrite this." --font scripts --size 8mm
uv run plot "Big and bold" --font "Avenir Next Bold" --size 30mm --fill
uv run plot drawing.svg
uv run plot toolpath.gcode
uv run plot design.hpgl
uv run plot letter.txt --font timesr
uv run plot photo.jpg
```

What it takes:

| Input | Notes |
| --- | --- |
| Text | Placed at the top-left, wrapped to the page. `\n` starts a new line. `-` reads stdin. Single-stroke fonts are plain ASCII: smart quotes and dashes become plain ones and accents are dropped; anything else is skipped with a note |
| Fonts | Single-stroke fonts (`futural`, `scripts`, `timesr`, `gothiceng`…) write like a pen. Any font installed on the Mac works too (`Helvetica`, `"Avenir Next Bold"`, `Georgia`…), drawn as outlines; `--fill` hatches them in. `plot fonts avenir` searches |
| SVG | Every path, scaled to fill the page (`--no-fit` keeps its real size). Fills are drawn as outlines |
| G-code | G0–G3 in mm or inches, absolute or relative. Pen down at Z ≤ 0 or M3, up at M5; with neither, G1 draws and G0 travels. Real size |
| HPGL | PU/PD/PA/PR, as Inkscape's "Save as HPGL" writes it. Real size |
| Images | PNG, JPG, GIF… drawn as crosshatching: darker areas get more directions of lines |

Layout options for all of them: `--fit` / `--no-fit`, `--scale 0.5`, `--rotate 90`,
`--at X Y` (top-left corner, mm from the paper's lower-left), `--hatch 1.0` (mm between
hatch lines). Anything too big for the paper is shrunk to fit, with a note.

Paper: `--paper letter` (default), `a4`, `a5`, `half-letter`, `max` (the whole 15 × 10"
bed) or a size like `200x150` (mm) or `8x6in`; add `-portrait` to turn it. Every size is
centered on the same spot; `plot park` shows where its lower-left corner goes.

`uv run plot dance` shows off: a minute of figure eights, spirals, a rose, a heart and
"HI!" written in the air, with the pen up and the pen-lift relay keeping the beat.
`plot dance --pen` draws it instead, as a spirograph-style picture (about 2 minutes).

Before plotting, `--preview job.png` (or `.svg`) writes a picture of the plan, and
`--dry-run` stops there. Ctrl-C (or Stop in the studio) halts the pen and lifts it.

## Plotter settings

Both input modules (X on top, the one with the sweep; Y below):

| Control | Setting | Why |
| --- | --- | --- |
| Range knob | **200** (mV/in) | 0–4.1 V then spans about 20", covering the 15 × 10" bed with room to spare |
| CAL / VAR | **CAL** | Fixed, accurate scale. VAR adds the fine-adjust knob, which drifts |
| MV / SEC (X only) | **MV** | SEC is the built-in time sweep |
| RESET / SWEEP (X only) | **RESET** | Otherwise X sweeps by itself |
| IN / CM | **IN** | |
| ×1 / ×10 | **×1** | |
| ZERO | **Leave alone** | Sets where 0 V lands. If one gets bumped, redo the origin (`plot jog`) |

Seen from the knob panel, X runs left to right (the arm moves) and Y runs away from you
(the pen carriage moves along the arm). Put paper in landscape, long side parallel to
the panel, and read drawings from the panel side.

## Setting up paper

With paper and a pen in, `uv run plot setup` does the first-time pass in about 6
minutes: it sets the scale from the bed's rulers, draws the tuning sheet and saves the
speed and pen timing you pick. The steps below are the same thing by hand.

1. `uv run plot park` moves the pen to where the paper's lower-left corner goes (and
   checks the plotter answers).
2. With no pen in: `uv run plot pen down`, then `uv run plot pen up`. If "down" lifts the
   holder, run `uv run plot pen flip` (saved on the Arduino).
3. Put a letter sheet down, landscape, with its lower-left corner under the pen tip.
   The bed's suction holds it.
4. `uv run plot jog`, then `t` traces the paper's edge with the pen up. If it's off,
   jog the pen over the paper's lower-left corner and press `o` to save that as the
   origin. Arrows move the pen; up arrow is +Y.
5. Calibrate the scale, either way round:
   - `uv run plot calibrate --rulers` (no pen needed) moves the pen to two spots and
     asks what the plotter's own rulers read there.
   - `uv run plot calibrate` (with a pen) draws an L of known size and asks for the
     lengths you measure.

   Both save to `plotter.toml`. The paper's center stays put, so its corner moves a
   little: run `plot park` again before placing paper.
6. With a new pen, `uv run plot tune` draws a tuning sheet: the same shapes at six
   speeds, and rows of dashes with five pen timings, each labeled. Set `draw_speed` to
   the fastest that still looks clean, and `pen_down_ms` / `pen_up_ms` to the shortest
   with whole dashes and no drag marks between them.
7. `uv run plot test` draws a test pattern: square with diagonals, circle, star, a fan
   of lines and text. Wobbly or overshooting corners: lower `draw_speed` or `accel`.

## Settings

`plotter.toml` holds the serial port, calibration, paper, speeds and pen timing, with
comments. `plot jog` and `plot calibrate` update it in place.

## Firmware

`src/` is the Uno firmware. It boots with the pen up and parked mid-scale, queues
commands and answers each line with `ok` or `error: ...`. To poke at it by hand:
`pio device monitor`, then `H` for help.

| Command | |
| --- | --- |
| `M x y ms` | straight line to (x, y) DAC counts (0–4095) over ms; 0 jumps |
| `U` / `D` | pen up / down |
| `W ms` | wait |
| `P [0\|1]` | show or set which relay level lifts the pen (saved in EEPROM) |
| `?` | status, answered immediately |
| `!` | stop: clear the queue and lift the pen, immediately |

If the pen is left down with nothing to do for 10 s, the firmware lifts it. The status
line's `late=` counts how often the queue ran dry before a timed move: once per job is
normal, more means the Mac fell behind and the pen paused mid-stroke.

Every connection restarts the Uno: macOS raises DTR whenever the port opens, and
that's wired to the Uno's reset. While it restarts, pin 9 floats and the relay drops,
which with the current wiring dips the pen once wherever it is. So every command ends
with the pen resting at the paper's lower-left corner, where that dot is harmless.
The real fix is swapping the relay's NO and NC wires (then `plot pen flip`), so a
dropped relay means pen up. The studio page keeps one connection open, so it
restarts the Uno only when it starts.

## Hardware notes

From photos of the shield (no schematic survives):

- MCP4822 on SPI: D13 SCK, D11 MOSI, D10 chip select, LDAC tied low. Channel A drives X+,
  channel B drives Y+. Each input's − post is jumpered to its ground post, and the Uno's
  ground goes to the X ground post.
- JZC-11F 5 V relay on D9 with a flyback diode switches the pen lift. There's no visible
  transistor; if the coil is driven straight from D9 it draws roughly 70–90 mA, about
  twice what an ATmega pin is rated for. A 2N3904 and a 1k base resistor would fix it.
- During a reset or upload, D9 floats and the relay drops. Wiring it so the released
  relay means pen up (move the wire between the relay's NO and NC contacts, then
  `plot pen flip`) keeps a reset from ever lowering the pen.
- The bed's suction pump runs whenever the plotter is on.

## Development

```bash
uv run pytest                    # planner, inputs, fonts, UI, and the firmware in the simulator
uv run plot --sim test           # a whole job on the simulated firmware; draws .pio/sim/last-run.png
uv run plot --sim ui             # the studio, plotting to the simulator
```

`host/sim` compiles the firmware sources for the Mac against a small fake Arduino layer,
so the real firmware code runs without the plotter. `host/hiplot` is the Python side:
`sources.py` (inputs), `fonts.py`, `planner.py` (motion), `device.py` (serial),
`ui.py` + `ui.html` (studio). `legacy/` is the 2020 sketch.
