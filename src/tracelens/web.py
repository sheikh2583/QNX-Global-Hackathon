"""``tracelens serve``: the TraceLens web app (Render, or any machine). Standard library only.

  /                 what TraceLens solves, how to use it, measured proof
  /demo             guided demo for judges: one real QNX 8.0 recording from bug to proven fix, then reliability
  /analyze          upload a recording (optionally C source and deadlines): plain-language report and patch
                    (reports also carry the radar's learned findings, bundled model, no network)
  /examples         the five real QNX programs; /example/<w> their reports, /proof/<w> their before/after
  /guide            how to read a report
  /replay/<bundle>  a real fix on the QNX VM, replayed step by step (from its recorded events.jsonl)
  /trace/<name>     engineer's view of a committed trace (full detector report)
  /healthz          liveness

Hosting on a small instance (Render's free tier has 512 MB): `tracelens serve --prebuild` renders the
pages built from committed traces once, one trace per subprocess (the largest real trace needs
~380 MB to analyze), into <root>/.site; the running server then only serves files. Uploads stay
live, capped and one at a time. The QNX target is not reachable from a hosting provider, so proof on
the kernel is shown from the recorded runs in docs/results.
"""

from __future__ import annotations

import gzip
import subprocess
import sys
import threading
from collections import OrderedDict
from email.parser import BytesParser
from email.policy import default as email_policy
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import __version__, app
from .analyze import Analysis, analyze_file, analyze_text
from .ml.radar import annotate as radar_annotate
from .config import Config, load_config

MAX_UPLOAD = 12 * 1024 * 1024  # ~150k events: about 200 MB to analyze
MAX_TEXT = 12 * 1024 * 1024
_ANALYZE = threading.BoundedSemaphore(1)  # one upload analysis at a time keeps memory bounded
WORKLOADS = list(app.WORKLOADS)


class Site:
    """Paths into the repository checkout the server runs from, plus a small analysis cache."""

    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self.real = self.root / "fixtures" / "real"
        self.results = self.root / "docs" / "results"
        self.cfg = load_config(self.real / "tracelens.toml") if (self.real / "tracelens.toml").exists() else Config()
        self.site_dir = self.root / ".site"
        self._cache: OrderedDict[str, Analysis] = OrderedDict()
        self._lock = threading.Lock()

    def traces(self) -> dict[str, Path]:
        """name -> committed real trace (buggy and reference builds of every workload)."""
        out = {}
        for w in WORKLOADS:
            for name in (w, f"{w}_fixed"):
                p = self.real / f"{name}.txt.gz"
                if p.exists():
                    out[name] = p
        return out

    def analysis(self, name: str) -> Analysis:
        with self._lock:
            if name in self._cache:
                self._cache.move_to_end(name)
                return self._cache[name]
        a = analyze_file(self.traces()[name], self.cfg)  # outside the lock: slow, and safe to repeat
        radar_annotate(a)  # learned findings for behaviour no rule knows (MEDIUM, never a fix)
        with self._lock:
            self._cache[name] = a
            while len(self._cache) > 2:  # keep memory small on a free instance
                self._cache.popitem(last=False)
        return a

    def sources(self, workload: str) -> dict[str, str]:
        d = self.root / "bugzoo" / workload
        return {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.glob("*.c"))}

    def results_data(self) -> app.Results:
        return app.Results(self.root)

    def replays(self) -> dict[str, Path]:
        """bundle name -> recorded events of a real fix (docs/results/fixes/<bundle>/events.jsonl)."""
        d = self.results / "fixes"
        return {p.parent.name: p for p in sorted(d.glob("*/events.jsonl"))} if d.is_dir() else {}


# ----------------------------------------------------------------------------- engineer's view
def _bar(extra: str = "") -> str:
    return (f'<div style="display:flex;flex-wrap:wrap;gap:8px 18px;padding:10px 16px;font:14px system-ui;'
            f'border-bottom:1px solid #ddd"><a href="/"><b>TraceLens</b></a>{extra}</div>')


def trace_page(site: Site, name: str) -> bytes:
    from .report.html import render
    w = name.removesuffix("_fixed")
    extra = (f'<a href="/example/{w}">Plain-language report</a><a href="/proof/{w}">Proven on QNX</a>'
             if not name.endswith("_fixed") else f'<a href="/trace/{w}">The buggy build</a>')
    return render(site.analysis(name)).replace("<main>", f"{_bar(extra)}<main>", 1).encode("utf-8")


# ----------------------------------------------------------------------------- pages from committed traces
def example_page(site: Site, w: str) -> bytes:
    return app.example_report(site.analysis(w), site.cfg, w, site.sources(w))


def demo_page(site: Site) -> bytes:
    w = "z1_infusion_pump"
    return app.demo_page(site.analysis(w), site.cfg, site.results_data(), site.sources(w))


def render_one(root: str | Path, name: str) -> None:
    """Write every page that needs the analysis of one committed trace into .site/."""
    site = Site(root)
    out = site.site_dir
    (out / "trace").mkdir(parents=True, exist_ok=True)
    (out / "trace" / f"{name}.html").write_bytes(trace_page(site, name))
    if name in WORKLOADS:
        (out / "example").mkdir(parents=True, exist_ok=True)
        (out / "example" / f"{name}.html").write_bytes(example_page(site, name))
    if name == "z1_infusion_pump":
        (out / "demo.html").write_bytes(demo_page(site))


def prebuild(root: str | Path = ".") -> int:
    """Render every committed trace's pages, each in its own process so memory is freed after it."""
    site = Site(root)
    failed = 0
    for name in site.traces():
        cp = subprocess.run([sys.executable, "-m", "tracelens.web", "render-one", str(site.root), name])
        print(f"  {'ok ' if cp.returncode == 0 else 'FAILED'} {name}", flush=True)
        failed += cp.returncode != 0
    return 1 if failed else 0


# ----------------------------------------------------------------------------- uploads
def parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str, bytes]]:
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    out = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            out[name] = (part.get_filename() or "", part.get_payload(decode=True) or b"")
    return out


def _text(data: bytes) -> str:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
        if len(data) > MAX_TEXT:
            raise ValueError("the recording is over 12 MB once unpacked; record a shorter run")
    return data.decode("utf-8", errors="replace")


class UploadError(ValueError):
    pass


def analyze_upload(fields: dict[str, tuple[str, bytes]]) -> bytes:
    if "trace" not in fields or not fields["trace"][1]:
        raise UploadError("Choose a recording file first.")
    cfg = Config()
    if fields.get("config", ("", b""))[1]:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tracelens.toml"
            p.write_bytes(fields["config"][1])
            cfg = load_config(p)
    try:
        a = analyze_text(_text(fields["trace"][1]), cfg)
    except Exception as exc:
        raise UploadError(f"It does not read as a QNX kernel trace ({exc}). Upload the text that "
                          "`traceprinter -f trace.kev` prints, or that text gzipped.") from exc
    if not a.model.events:
        raise UploadError("There are no QNX kernel events in it. Upload the text that `traceprinter -f trace.kev` "
                          "prints, or that text gzipped.")
    radar_annotate(a)
    src_name, src = fields.get("source", ("", b""))
    sources = {Path(src_name or "main.c").name: src.decode("utf-8", errors="replace")} if src else None
    return app.upload_report(a, cfg, fields["trace"][0], sources)


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    site: Site = None  # set by make_server
    server_version = f"TraceLens/{__version__}"

    def log_message(self, fmt, *args):  # quiet, single-line logs
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' "
                         "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str):
        body = (f'<section class=hero><div class=eyebrow>{status}</div><h1>{escape(message)}</h1>'
                f'<div class=btns><a class="btn primary" href="/">Home</a>'
                f'<a class="btn ghost" href="/demo">Guided demo</a></div></section>')
        self._send(app.layout("TraceLens", body), status)

    def _cached(self, rel: str) -> bytes | None:
        p = self.site.site_dir / rel
        return p.read_bytes() if p.exists() else None

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        site = self.site
        path = unquote(self.path.split("?", 1)[0]).rstrip("/") or "/"
        parts = path.strip("/").split("/")
        try:
            if path == "/healthz":
                return self._send(b"ok\n", ctype="text/plain")
            if path == "/":
                return self._send(app.home(site.results_data()))
            if path == "/demo":
                return self._send(self._cached("demo.html") or demo_page(site))
            if path == "/analyze":
                return self._send(app.analyze_page())
            if path == "/guide":
                return self._send(app.guide_page())
            if path == "/live.js":
                from .live import live_js
                return self._send(live_js(), ctype="text/javascript; charset=utf-8")
            if len(parts) == 2 and parts[0] == "replay" and parts[1] in site.replays():
                w = parts[1].split("_codelab")[0]
                name = app.WORKLOADS.get(w, (parts[1],))[0]
                return self._send(app.live_page("replay", f"/replay/{parts[1]}/events.json", f"Fixing the {name.lower()}",
                                                "A real run of `tracelens fix` on our QNX 8.0 machine, recorded event by "
                                                "event and played back faster than it happened."))
            if len(parts) == 3 and parts[0] == "replay" and parts[2] == "events.json" and parts[1] in site.replays():
                lines = site.replays()[parts[1]].read_text(encoding="utf-8").splitlines()
                body = ("[" + ",".join(line for line in lines if line.strip()) + "]").encode("utf-8")
                return self._send(body, ctype="application/json")
            if path == "/examples":
                return self._send(app.examples_page(site.results_data()))
            if len(parts) == 2 and parts[0] == "example" and parts[1] in WORKLOADS:
                return self._send(self._cached(f"example/{parts[1]}.html") or example_page(site, parts[1]))
            if len(parts) == 2 and parts[0] == "trace" and parts[1] in site.traces():
                return self._send(self._cached(f"trace/{parts[1]}.html") or trace_page(site, parts[1]))
            if len(parts) == 2 and parts[0] in ("proof", "fix") and parts[1] in WORKLOADS:
                p = site.results / "fixes" / parts[1] / "report.html"
                if p.exists():
                    extra = f'<a href="/example/{parts[1]}">Plain-language report</a><a href="/demo">Guided demo</a>'
                    return self._send(p.read_text(encoding="utf-8").replace("<main>", f"{_bar(extra)}<main>", 1)
                                      .encode("utf-8"))
            if len(parts) == 2 and parts[0] == "remedy" and parts[1] in WORKLOADS:  # old links
                return self._send(b"", 301, headers=[("Location", f"/example/{parts[1]}")])
            return self._error(404, "There is no page here.")
        except Exception as exc:  # a demo must answer, not hang
            print(f"error on {path}: {type(exc).__name__}: {exc}", flush=True)
            return self._error(500, "Something went wrong on our side. Please try another page.")

    def do_POST(self):
        if self.path.split("?", 1)[0] not in ("/analyze", "/upload"):
            return self._error(404, "There is no page here.")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD + 1024 * 1024:
            return self._send(app.analyze_page("The recording must be under 12 MB. Record a shorter run, or "
                                               "gzip the text."), 413)
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return self._send(app.analyze_page("Send the form from this page."), 400)
        if not _ANALYZE.acquire(timeout=90):
            return self._send(app.analyze_page("Another recording is being analyzed. Try again in a minute."), 503)
        try:
            return self._send(analyze_upload(parse_multipart(ctype, self.rfile.read(length))))
        except UploadError as exc:
            return self._send(app.analyze_page(str(exc)), 400)
        except Exception as exc:
            print(f"upload error: {type(exc).__name__}: {exc}", flush=True)
            return self._send(app.analyze_page("TraceLens could not analyze this recording. Check that it is "
                                               "traceprinter output from QNX 7 or 8."), 400)
        finally:
            _ANALYZE.release()


def make_server(host: str = "127.0.0.1", port: int = 8000, root: str | Path = ".") -> ThreadingHTTPServer:
    handler = type("TraceLensHandler", (Handler,), {"site": Site(root)})
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = "127.0.0.1", port: int = 8000, root: str | Path = ".") -> None:
    httpd = make_server(host, port, root)
    print(f"TraceLens {__version__} on http://{host}:{port}/ (root {Path(root).resolve()})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "render-one":
    render_one(sys.argv[2], sys.argv[3])
