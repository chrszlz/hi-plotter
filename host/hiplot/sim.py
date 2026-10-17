"""Builds the firmware simulator: the real firmware sources compiled for the Mac
against a fake Arduino layer (host/sim)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted((ROOT / "src").glob("*.cpp")) + [ROOT / "host/sim/sim_main.cpp"]
HEADERS = sorted((ROOT / "src").glob("*.h")) + sorted((ROOT / "host/sim/fake").glob("*.h"))
BINARY = ROOT / ".pio/sim/firmware-sim"


def build() -> Path:
    """Compiles the simulator if any source is newer than the binary."""
    newest = max(p.stat().st_mtime for p in SOURCES + HEADERS)
    if BINARY.exists() and BINARY.stat().st_mtime >= newest:
        return BINARY

    BINARY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["c++", "-std=c++17", "-O2", "-Wall", "-Wextra",
         "-I", str(ROOT / "host/sim/fake"), "-I", str(ROOT / "src"),
         *map(str, SOURCES), "-o", str(BINARY)],
        check=True,
    )
    return BINARY


def read_log(path: Path) -> list[tuple[int, int, int, bool]]:
    """The sim's record of every DAC or pen change: (time_us, x, y, pen_down)."""
    rows = []
    for line in path.read_text().splitlines():
        t, x, y, pen = line.split()
        rows.append((int(t), int(x), int(y), pen == "1"))
    return rows
