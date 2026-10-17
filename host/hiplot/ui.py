"""`plot ui`: a local web page to type text, pick a font, drop in a file, see a preview
and plot it. Serves on 127.0.0.1 only."""

import base64
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import fonts, jobs, planner, preview, sim, sources, tuning
from .config import PAPERS, Config
from .device import Plotter, PlotterError, SimTransport

PAGE = Path(__file__).with_name("ui.html")
SIM_LOG = sim.ROOT / ".pio/sim/ui.log"
MAX_UPLOAD = 30 * 1024 * 1024


class Studio:
    """The plotter connection and the job in progress, shared by all requests."""

    def __init__(self, config: Config, sim_mode: bool):
        self.config = config
        self.sim_mode = sim_mode
        self.plotter: Plotter | None = None
        self.device_lock = threading.Lock()
        self.start_lock = threading.Lock()  # one job at a time, even with a double click
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = {"state": "idle", "progress": 0.0, "left": 0.0, "message": ""}

    # MARK: - Requests

    def job_maker(self, request: dict):
        """(make_job(start position in mm), config) for a request: text, a file, or a
        built-in sheet ("test" or "tune")."""
        config = self.config.with_paper(request["paper"]) if request.get("paper") else self.config
        builtin = request.get("builtin")
        if builtin == "tune":
            return (lambda start: tuning.job(config, start)), config
        drawing = sources.test_pattern(config) if builtin == "test" else self.drawing(request, config)
        return (lambda start: jobs.prepare(drawing, config, start)), config

    def drawing(self, request: dict, config: Config) -> sources.Drawing:
        style = sources.TextStyle(
            font=request.get("font") or "futural",
            size=fonts.parse_size(request.get("size") or 10),
            align=request.get("align") or "left",
            line_spacing=float(request.get("lineSpacing") or 1.4),
            fill=bool(request.get("fill")),
        )
        fit = {"auto": None, "fit": True, "actual": False}[request.get("fit") or "auto"]
        layout = sources.Layout(
            fit=fit,
            scale=float(request.get("scale") or 1),
            rotate=int(request.get("rotate") or 0),
            hatch=float(request.get("hatch") or 0.8),
            image=request.get("image") or "auto",
        )
        upload = request.get("file")
        if upload:
            data = base64.b64decode(upload["data"])
            return sources.load_bytes(data, upload["name"], config, style, layout)
        content = request.get("text") or ""
        if not content.strip():
            raise sources.SourceError("Type some text or drop in a file")
        return sources.text(content, config, style, layout)

    def preview(self, request: dict) -> dict:
        make_job, config = self.job_maker(request)
        job = make_job(0j)
        down, up = job.preview_strokes(config)
        return {
            "svg": preview.svg(config, down, up, job.drawing.name),
            "summary": job.summary,
            "notes": job.drawing.notes,
        }

    def plot(self, request: dict) -> dict:
        make_job, config = self.job_maker(request)
        with self.start_lock:
            if self.busy:
                raise PlotterError("Already plotting")
            self.stop_event.clear()
            self.state = {"state": "starting", "progress": 0.0, "left": 0.0, "message": "Connecting..."}
            self.thread = threading.Thread(target=self._run, args=(make_job, config), daemon=True)
            self.thread.start()
        return {"ok": True}

    def _run(self, make_job, config: Config):
        try:
            with self.device_lock:
                plotter = self._connect()
                job = make_job(jobs.position_mm(plotter, config))
                self.state = {"state": "plotting", "progress": 0.0, "left": job.plan.duration_ms / 1000,
                              "message": job.summary}

                def progress(fraction: float, left: float):
                    self.state.update(progress=fraction, left=left)

                jobs.stream(plotter, job, progress, self.stop_event)
            self.state = {"state": "idle", "progress": 1.0, "left": 0.0, "message": f"Done: {job.drawing.name}"}
        except jobs.Stopped:
            with self.device_lock:
                jobs.rest(plotter, config)
            self.state = {"state": "idle", "progress": 0.0, "left": 0.0,
                          "message": "Stopped. Pen lifted and moved to the paper corner."}
        except Exception as error:  # report anything to the page rather than dying silently
            self.state = {"state": "error", "progress": 0.0, "left": 0.0, "message": str(error)}
            self._disconnect()

    def stop(self) -> dict:
        self.stop_event.set()
        if not self.busy and self.plotter:
            with self.device_lock:
                self.plotter.stop()
                jobs.rest(self.plotter, self.config)
        return {"ok": True}

    def pen(self, request: dict) -> dict:
        with self._idle_device() as plotter:
            plotter.send("D" if request.get("down") else "U")
        return {"ok": True}

    def park(self) -> dict:
        with self._idle_device() as plotter:
            jobs.rest(plotter, self.config)
        return {"ok": True}

    def close(self):
        """Leaves the pen at the paper corner (see jobs.rest) and disconnects."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.plotter:
            try:
                with self.device_lock:
                    jobs.rest(self.plotter, self.config)
            finally:
                self._disconnect()

    def status(self) -> dict:
        return {**self.state, "connected": self.plotter is not None, "sim": self.sim_mode}

    def sim_drawing(self) -> str:
        if not self.sim_mode or not SIM_LOG.exists():
            return preview.svg(self.config, [], [])
        rows = sim.read_log(SIM_LOG)
        down, _ = preview.from_sim_log(rows, self.config)
        return preview.svg(self.config, down, [], "Simulator")

    # MARK: - Device

    @property
    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _connect(self) -> Plotter:
        if self.plotter is None:
            if self.sim_mode:
                self.plotter = Plotter(SimTransport(sim.build(), SIM_LOG))
            else:
                self.plotter = Plotter.open(self.config.port, self.config.baud)
        return self.plotter

    def _disconnect(self):
        if self.plotter:
            try:
                self.plotter.transport.close()
            except Exception:
                pass
        self.plotter = None

    def _idle_device(self):
        if self.busy:
            raise PlotterError("Busy plotting")
        studio = self

        class Session:
            def __enter__(self):
                studio.device_lock.acquire()
                try:
                    return studio._connect()
                except Exception:
                    studio.device_lock.release()
                    raise

            def __exit__(self, kind, error, trace):
                studio.device_lock.release()
                if error is not None and not isinstance(error, PlotterError):
                    studio._disconnect()

        return Session()


def _font_list() -> dict:
    return {
        "fonts": [{"name": name, "kind": kind} for name, kind in fonts.names()],
        "papers": list(PAPERS),
    }


def serve(config: Config, sim_mode: bool = False, port: int = 8800, open_browser: bool = True):
    studio = Studio(config, sim_mode)
    if sim_mode:
        SIM_LOG.unlink(missing_ok=True)  # a fresh simulated sheet of paper

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes = {
                "/": lambda: (PAGE.read_bytes(), "text/html; charset=utf-8"),
                "/api/fonts": lambda: (json.dumps(_font_list()).encode(), "application/json"),
                "/api/status": lambda: (json.dumps(studio.status()).encode(), "application/json"),
                "/api/sim.svg": lambda: (studio.sim_drawing().encode(), "image/svg+xml"),
            }
            route = routes.get(self.path.split("?")[0])
            if route is None:
                self._reply(404, b"not found", "text/plain")
                return
            self._reply(200, *route())

        def do_POST(self):
            routes = {
                "/api/preview": studio.preview,
                "/api/plot": studio.plot,
                "/api/stop": lambda request: studio.stop(),
                "/api/pen": studio.pen,
                "/api/park": lambda request: studio.park(),
            }
            route = routes.get(self.path)
            if route is None:
                self._reply(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self._json(413, {"error": "That file is too big (30 MB max)"})
                return
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
                self._json(200, route(request))
            except (sources.SourceError, fonts.FontNotFound, planner.OutOfRange, PlotterError, ValueError) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self._json(500, {"error": f"{type(error).__name__}: {error}"})

        def _json(self, status: int, body: dict):
            self._reply(status, json.dumps(body).encode(), "application/json")

        def _reply(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            break
        except OSError:
            continue
    else:
        raise OSError(f"No free port between {port} and {port + 19}")

    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Plotter studio: {url}  ({'simulator' if sim_mode else 'plotter'}; Ctrl-C to quit)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        studio.close()
        server.server_close()
