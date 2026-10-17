"""Talking to the firmware: the real Arduino over USB serial, or the simulator."""

import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import serial
from serial.tools import list_ports

# USB vendor IDs of Arduino boards and the usual clone USB-serial chips.
ARDUINO_VENDOR_IDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}

BANNER = "# hi-plotter"
STATUS = re.compile(r"<(\w+) x=(\d+) y=(\d+) pen=(\w+) q=(\d+)(?: late=(\d+))?>")


class PlotterError(Exception):
    pass


@dataclass
class Status:
    idle: bool
    x: int
    y: int
    pen_down: bool
    queued: int
    # Times the firmware's queue ran dry before a timed command: 1 per job is normal.
    late: int = 0


# MARK: - Transports


class SerialTransport:
    def __init__(self, port: str, baud: int):
        # Opening the port restarts the Uno (macOS raises DTR on every open, whatever
        # the termios settings). Exclusive, so a second program can't interleave
        # commands with this one.
        try:
            self.serial = serial.Serial(port, baud, timeout=0.05, exclusive=True)
        except serial.SerialException as error:
            busy = "busy" in str(error).lower() or "lock" in str(error).lower()
            raise PlotterError(
                f"{port} is in use by another program (is `plot ui` running?)" if busy
                else f"Can't open {port}: {error}"
            ) from error
        self.buffer = b""

    def write(self, data: bytes):
        self.serial.write(data)

    def readline(self, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            # Take whatever has arrived (waiting for at most one byte): asking for more
            # than is there would sit out the whole timeout on every short reply.
            chunk = self.serial.read(max(1, self.serial.in_waiting))
            if chunk:
                self.buffer += chunk
            elif time.monotonic() > deadline:
                return None
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line.decode(errors="replace").strip()

    def close(self):
        self.serial.close()


class SimTransport:
    """Runs the firmware simulator (host/sim) as a subprocess."""

    def __init__(self, binary: Path, log_path: Path | None = None):
        env = {"SIM_LOG": str(log_path)} if log_path else {}
        self.process = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, bufsize=0
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for raw in self.process.stdout:
            self.lines.put(raw.decode(errors="replace").strip())
        self.lines.put(None)

    def write(self, data: bytes):
        self.process.stdin.write(data)

    def readline(self, timeout: float) -> str | None:
        try:
            return self.lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        """Closes the sim's input and waits for it to finish what's queued."""
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        self.process.wait(timeout=600)


def find_port() -> str:
    """The Arduino's serial port, if exactly one is plugged in."""
    candidates = [
        p.device for p in list_ports.comports()
        if p.vid in ARDUINO_VENDOR_IDS or "usbmodem" in p.device or "usbserial" in p.device
    ]
    # macOS lists each port twice; /dev/cu.* is the one for outgoing connections.
    candidates = sorted({c.replace("/dev/tty.", "/dev/cu.") for c in candidates})
    if not candidates:
        raise PlotterError("No Arduino found. Is the USB cable plugged in?")
    if len(candidates) > 1:
        raise PlotterError(f"Several serial ports found, set one in plotter.toml: {', '.join(candidates)}")
    return candidates[0]


# MARK: - Plotter


class Plotter:
    def __init__(self, transport, log: Callable[[str], None] = lambda line: None):
        self.transport = transport
        self.log = log
        # Whether connecting restarted the board (it announced itself) or found it running.
        self.restarted = False
        self.wait_ready()

    @classmethod
    def open(cls, port: str, baud: int, **kwargs) -> "Plotter":
        return cls(SerialTransport(port or find_port(), baud), **kwargs)

    def wait_ready(self, timeout: float = 3.0):
        """Asks for status straight away. A board that's already running answers at once;
        one that's restarting misses the question in its bootloader and prints its
        banner when the firmware is up."""
        self.transport.write(b"?")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.transport.readline(0.2)
            if line is None:
                continue
            if STATUS.match(line):
                return
            if line.startswith(BANNER):
                self.restarted = True
                # If the question did reach the fresh firmware, drop its answer so it
                # isn't mistaken for the reply to a later one.
                self.transport.readline(0.3)
                return
        # Neither: ask for the version in case a line got lost.
        self.transport.write(b"\nV\n")
        for _ in range(20):
            line = self.transport.readline(0.25)
            if line is not None and line.startswith(BANNER):
                self._read_until_ok()
                return
        raise PlotterError("The plotter didn't answer. Is the hi-plotter firmware uploaded?")

    # MARK: - Commands

    def send(self, line: str) -> list[str]:
        """Sends one command and waits for its "ok". Returns any "#" info lines."""
        self.transport.write(line.encode() + b"\n")
        return self._read_until_ok(line)

    def _read_until_ok(self, sent: str = "") -> list[str]:
        info = []
        while True:
            line = self.transport.readline(30)
            if line is None:
                raise PlotterError(f"No reply to {sent!r}")
            if line == "ok":
                return info
            if line.startswith("error"):
                raise PlotterError(f"{sent!r}: {line}")
            if line.startswith("#"):
                info.append(line)
                self.log(line)

    def run(self, commands: Iterable[str], progress: Callable[[int], None] | None = None):
        """Streams commands. The firmware queues them and answers "ok" as soon as there's
        room, so this stays ahead of the pen."""
        for i, line in enumerate(commands):
            self.send(line)
            if progress:
                progress(i + 1)

    def status(self) -> Status:
        self.transport.write(b"?")
        while True:
            line = self.transport.readline(2)
            if line is None:
                raise PlotterError("No status reply")
            match = STATUS.match(line)
            if match:
                state, x, y, pen, queued, late = match.groups()
                return Status(state == "idle", int(x), int(y), pen == "down", int(queued), int(late or 0))
            self.log(line)

    def wait_idle(self, poll: float = 0.2):
        while not self.status().idle:
            time.sleep(poll)

    def stop(self):
        """Clears the firmware's queue and lifts the pen, right away."""
        self.transport.write(b"!")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = self.transport.readline(0.5)
            if line == "# stopped":
                return

    def pen_up_level(self) -> int:
        """The relay level that lifts the pen (0 or 1), from the firmware."""
        for line in self.send("P"):
            match = re.search(r"pen up level: (\d)", line)
            if match:
                return int(match.group(1))
        raise PlotterError("Couldn't read the pen setting")

    def close(self):
        self.transport.close()
