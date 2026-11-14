"""``tracelens serve``: the hosted demo (Render, or any machine). Standard library only.

Everything here is TraceLens itself running live on the server:

  /                     the results page (real QNX 8.0 numbers) with a "try it" panel
  /trace/<name>         live analysis of a committed real QNX trace (HTML report)
  /remedy/<name>        the QNX fix for that trace, planned live from the trace + the workload source
  /fix/<workload>       the before/after report of that fix, proven on a QNX 8.0 VM (recorded runs)
  /upload  (POST)       analyze your own traceprinter output; add C source to get a patch
  /healthz              liveness

Hosting on a small instance (Render's free tier has 512 MB): `tracelens serve --prebuild` renders the
committed-trace pages once, one trace per subprocess (the largest real trace needs ~380 MB to
analyze), into <root>/.site; the running server then only serves files. Uploads stay live, capped
and one at a time.

The QNX target is not reachable from a hosting provider, so proving a fix on the kernel is shown
from the recorded runs in docs/results; detection and fix planning run live.
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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import __version__
from .analyze import Analysis, analyze_file, analyze_text
from .config import Config, load_config
from .findings import at_least

MAX_UPLOAD = 12 * 1024 * 1024  # ~150k events: about 200 MB to analyze
MAX_TEXT = 12 * 1024 * 1024
_ANALYZE = threading.BoundedSemaphore(1)  # one upload analysis at a time keeps memory bounded
WORKLOADS = ["z1_infusion_pump", "z2_brake_by_wire", "z3_sensor_fusion", "z4_camera_pipeline", "z5_motor_encoder"]
LABELS = {"z1_infusion_pump": "Infusion pump", "z2_brake_by_wire": "Brake-by-wire", "z3_sensor_fusion": "Sensor fusion",
          "z4_camera_pipeline": "Camera pipeline", "z5_motor_encoder": "Motor encoder"}


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
        with self._lock:
            self._cache[name] = a
            while len(self._cache) > 2:  # keep memory small on a free instance
                self._cache.popitem(last=False)
        return a

    def sources(self, workload: str) -> dict[str, str]:
        d = self.root / "bugzoo" / workload
        return {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted(d.glob("*.c"))}


PAGE_CSS = """
:root{--bg:#f6f7f6;--surface:#fff;--fg:#17201d;--muted:#5b6763;--line:#dde3e0;--accent:#0f6e64;
--run:#2f9e44;--ready:#e8a317;--block:#d9363e;--intr:#1c7ed6;--code:#eef2f0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111615;--surface:#19201e;--fg:#e6ece9;
--muted:#9aa8a3;--line:#2b3532;--accent:#4fc4b4;--run:#40c057;--ready:#f5b83d;--block:#ff6b6b;--intr:#4dabf7;
--code:#1f2826;color-scheme:dark}}
:root[data-theme=dark]{--bg:#111615;--surface:#19201e;--fg:#e6ece9;--muted:#9aa8a3;--line:#2b3532;--accent:#4fc4b4;
--run:#40c057;--ready:#f5b83d;--block:#ff6b6b;--intr:#4dabf7;--code:#1f2826;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px max(16px,env(safe-area-inset-right,0px)) 64px
max(16px,env(safe-area-inset-left,0px));display:grid;gap:22px}.wrap>*{min-width:0}
a{color:var(--accent)}h1,h2{margin:0;line-height:1.2;text-wrap:balance}p{margin:0;max-width:70ch}
.bar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:14px;padding:10px 16px;
border-bottom:1px solid var(--line);background:var(--surface)}.bar b{color:var(--accent)}
.muted{color:var(--muted)}code,pre{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}
code{font-size:.88em;background:var(--code);padding:1px 5px;border-radius:4px}
pre{margin:0;padding:12px;overflow-x:auto;background:var(--code);border-radius:10px;font-size:12.5px;line-height:1.55}
.add{color:var(--run)}.del{color:var(--block)}.hunk{color:var(--intr)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:grid;gap:8px}
.tag{display:inline-block;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;margin-right:6px}
.auto{background:rgba(47,158,68,.14);color:var(--run)}.guided{background:rgba(28,126,214,.14);color:var(--intr)}
.symptom{background:var(--code);color:var(--muted)}
ul{margin:0;padding-left:20px}
"""

TRY_CSS = """
.try{display:grid;gap:14px}.try table{border-collapse:collapse;width:100%;font-size:14px}
.try td,.try th{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
.try th{font:500 12px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.try .links a{margin-right:12px;white-space:nowrap}
.upload{display:grid;gap:10px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.upload label{display:grid;gap:4px;font-size:14px}.upload button{justify-self:start;font:600 14px var(--sans);
padding:8px 16px;border-radius:8px;border:0;background:var(--accent);color:var(--bg);cursor:pointer}
.upload button:focus-visible,.try a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def _bar(extra: str = "") -> str:
    return (f'<div class=bar><a href="/"><b>TraceLens</b></a><span class=muted>QNX 8.0 · live demo · '
            f'v{escape(__version__)}</span>{extra}</div>')


def _page(title: str, body: str, css: str = PAGE_CSS) -> bytes:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f'<meta name=viewport content="width=device-width,initial-scale=1"><title>{escape(title)}</title>'
            f"<style>{css}</style></head><body>{body}</body></html>").encode("utf-8")


def try_section(site: Site) -> str:
    traces = site.traces()
    rows = []
    for w in WORKLOADS:
        if w not in traces:
            continue
        fixed = f"{w}_fixed" in traces
        has_fix = (site.results / "fixes" / w / "report.html").exists()
        rows.append(
            f"<tr><td><b>{LABELS[w]}</b><br><span class=muted>{w}</span></td><td class=links>"
            f'<a href="/trace/{w}">Analyze the buggy trace</a>'
            f'<a href="/remedy/{w}">Plan the fix now</a>'
            + (f'<a href="/fix/{w}">Proven on QNX</a>' if has_fix else "")
            + (f'<a href="/trace/{w}_fixed">Hand-written fix</a>' if fixed else "") + "</td></tr>")
    return f"""
  <section class=try id=try>
    <div class=eyebrow>Try it live</div>
    <h2>Run TraceLens on real QNX 8.0 traces</h2>
    <p>TraceLens on this server parsed and analyzed each real trace and planned its fix from the trace and the
    program's C source (computed when the demo was deployed). A trace you upload below is analyzed live.
    Proving a fix on a QNX kernel needs a QNX target, so that step shows the recorded runs from our QNX 8.0 VM.</p>
    <div class=scroll><table><thead><tr><th>Program</th><th>Live</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <form class=upload method=post action="/upload" enctype="multipart/form-data">
      <b>Analyze your own trace</b>
      <label for=trace>traceprinter output (.txt or .txt.gz, up to 12 MB)
        <input id=trace name=trace type=file accept=".txt,.gz" required></label>
      <label for=source>Optional: your program's C source, to get a patch
        <input id=source name=source type=file accept=".c,.h"></label>
      <label for=config>Optional: tracelens.toml (deadlines, thresholds)
        <input id=config name=config type=file accept=".toml"></label>
      <button type=submit>Analyze</button>
    </form>
  </section>
"""


BAR_CSS = """
.bar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:14px;padding:10px 16px;
border-bottom:1px solid var(--line);background:var(--surface)}.bar b{color:var(--accent)}.bar a{text-decoration:none}
"""


def landing(site: Site) -> bytes:
    """The results page (its own head: title, fonts, tokens) plus the bar and the live panel."""
    from .report.showcase import render_showcase
    html = render_showcase(site.root, live=try_section(site))
    head, body = html.split("</style>", 1)
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            + head + TRY_CSS + BAR_CSS + "</style></head><body>"
            + _bar('<a href="#try">Try it live</a>') + body + "</body></html>").encode("utf-8")


def _diff_html(diff: str) -> str:
    from .report.fix_html import _diff_html as d
    return d(diff)


def remedy_page(title: str, a: Analysis, sources: dict[str, str], cfg: Config, back: str = "") -> bytes:
    import difflib
    from .remedy import plan

    findings = [f for f in a.findings if at_least(f.severity, cfg.fail_on)] or a.findings
    remedies, fixed = plan(findings, sources) if sources else ([], {})
    parts = [_bar(back), "<div class=wrap>", f"<h1>The fix for {escape(title)}</h1>",
             f'<p class=muted>Planned by TraceLens on this server from {len(a.findings)} findings in the trace and '
             f'{len(sources)} source file(s). Deterministic: the same trace and source always give this patch.</p>']
    if not sources:
        parts.append("<p>No C source was given, so TraceLens can only name the root cause. Upload the program's "
                     "source to get a patch.</p>")
    for r in remedies:
        kind = "symptom" if r.rule == "symptom" else ("auto" if r.automatic else "guided")
        locs = "".join(f"<li><code>{escape(p)}:{n}</code> <code>{escape(c)}</code></li>" for p, n, c in r.locations[:10])
        parts.append(
            f'<div class=card><div><span class="tag {kind}">{ {"auto": "automatic", "guided": "guided", "symptom": "symptom"}[kind] }</span>'
            f"<b>{escape(r.title)}</b></div><p>{escape(r.rationale)}</p>"
            + (f"<ul>{locs}</ul>" if locs else "")
            + "".join(f"<p>{escape(g)}</p>" for g in r.guidance)
            + "".join(f'<p class=muted>Not automatic: {escape(n)}</p>' for n in r.notes if not r.automatic)
            + "</div>")
    if not remedies and sources:
        parts.append("<p>Nothing to fix: no finding at or above the gate.</p>")
    diff = "".join(line for p in sorted(sources) if fixed.get(p, sources[p]) != sources[p]
                   for line in difflib.unified_diff(sources[p].splitlines(True), fixed[p].splitlines(True),
                                                    f"a/{p}", f"b/{p}"))
    if diff:
        parts.append(f"<h2>The patch</h2><pre>{_diff_html(diff)}</pre>")
    parts.append("</div>")
    return _page(f"Fix: {title}", "".join(parts))


def report_with_bar(a: Analysis, extra: str) -> bytes:
    from .report.html import render
    html = render(a)
    return html.replace("<main>", f"{_bar(extra)}<main>", 1).encode("utf-8")


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
            raise ValueError("the decompressed trace is over 12 MB; capture a shorter run for the demo")
    return data.decode("utf-8", errors="replace")


class Handler(BaseHTTPRequestHandler):
    site: Site = None  # set by make_server
    server_version = f"TraceLens/{__version__}"

    def log_message(self, fmt, *args):  # quiet, single-line logs
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' "
                         "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str):
        self._send(_page("TraceLens", f"{_bar()}<div class=wrap><h1>{status}</h1><p>{escape(message)}</p>"
                         '<p><a href="/">Back to the demo</a></p></div>'), status)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        site = self.site
        path = unquote(self.path.split("?", 1)[0]).rstrip("/") or "/"
        try:
            if path == "/healthz":
                return self._send(b"ok\n", ctype="text/plain")
            if path == "/":
                return self._send(landing(site))
            parts = path.strip("/").split("/")
            if len(parts) == 2 and parts[0] in ("trace", "remedy"):
                cached = site.site_dir / parts[0] / f"{parts[1]}.html"
                if parts[1] in site.traces() and cached.exists():
                    return self._send(cached.read_bytes())
            if len(parts) == 2 and parts[0] == "trace" and parts[1] in site.traces():
                name = parts[1]
                w = name.removesuffix("_fixed")
                extra = (f'<a href="/remedy/{w}">Plan the fix</a><a href="/fix/{w}">Proven on QNX</a>'
                         if not name.endswith("_fixed") else f'<a href="/trace/{w}">The buggy build</a>')
                return self._send(report_with_bar(site.analysis(name), extra))
            if len(parts) == 2 and parts[0] == "remedy" and parts[1] in WORKLOADS:
                w = parts[1]
                return self._send(remedy_page(LABELS[w], site.analysis(w), site.sources(w), site.cfg,
                                              f'<a href="/trace/{w}">The trace</a><a href="/fix/{w}">Proven on QNX</a>'))
            if len(parts) == 2 and parts[0] == "fix" and parts[1] in WORKLOADS:
                p = site.results / "fixes" / parts[1] / "report.html"
                if p.exists():
                    html = p.read_text(encoding="utf-8")
                    return self._send(html.replace("<main>", f"{_bar()}<main>", 1).encode("utf-8"))
            return self._error(404, "No such page.")
        except Exception as exc:  # a demo must answer, not hang
            return self._error(500, f"{type(exc).__name__}: {exc}")

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/upload":
            return self._error(404, "No such page.")
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD + 1024 * 1024:
            return self._error(413, "Upload up to 12 MB of traceprinter text (or .gz).")
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            return self._error(400, "Send the form as multipart/form-data.")
        try:
            if not _ANALYZE.acquire(timeout=90):
                return self._error(503, "The demo is busy analyzing another upload. Try again in a minute.")
            try:
                return self._upload(parse_multipart(ctype, self.rfile.read(length)))
            finally:
                _ANALYZE.release()
        except Exception as exc:
            return self._error(400, f"Could not analyze that file: {type(exc).__name__}: {exc}")

    def _upload(self, fields):
        try:
            if "trace" not in fields or not fields["trace"][1]:
                return self._error(400, "Choose a trace file.")
            cfg = Config()
            if fields.get("config", ("", b""))[1]:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "tracelens.toml"
                    p.write_bytes(fields["config"][1])
                    cfg = load_config(p)
            a = analyze_text(_text(fields["trace"][1]), cfg)
            if not a.model.events:
                return self._error(400, "Could not analyze that file: no QNX kernel events in it. Upload the "
                                        "text that `traceprinter -f trace.kev` prints (or that text gzipped).")
            src_name, src = fields.get("source", ("", b""))
            if src:
                sources = {Path(src_name or "main.c").name: src.decode("utf-8", errors="replace")}
                return self._send(remedy_page(fields["trace"][0] or "your trace", a, sources, cfg))
            from .report.html import render
            return self._send(render(a).replace("<main>", f"{_bar()}<main>", 1).encode("utf-8"))
        except Exception as exc:
            return self._error(400, f"Could not analyze that file: {type(exc).__name__}: {exc}")


def trace_page(site: Site, name: str) -> bytes:
    w = name.removesuffix("_fixed")
    extra = (f'<a href="/remedy/{w}">Plan the fix</a><a href="/fix/{w}">Proven on QNX</a>'
             if not name.endswith("_fixed") else f'<a href="/trace/{w}">The buggy build</a>')
    return report_with_bar(site.analysis(name), extra)


def render_one(root: str | Path, name: str) -> None:
    """Write .site/trace/<name>.html (and .site/remedy/<name>.html for a buggy build)."""
    site = Site(root)
    (site.site_dir / "trace").mkdir(parents=True, exist_ok=True)
    (site.site_dir / "trace" / f"{name}.html").write_bytes(trace_page(site, name))
    if name in WORKLOADS:
        (site.site_dir / "remedy").mkdir(parents=True, exist_ok=True)
        (site.site_dir / "remedy" / f"{name}.html").write_bytes(
            remedy_page(LABELS[name], site.analysis(name), site.sources(name), site.cfg,
                        f'<a href="/trace/{name}">The trace</a><a href="/fix/{name}">Proven on QNX</a>'))


def prebuild(root: str | Path = ".") -> int:
    """Render every committed trace's pages, each in its own process so memory is freed after it."""
    site = Site(root)
    failed = 0
    for name in site.traces():
        cp = subprocess.run([sys.executable, "-m", "tracelens.web", "render-one", str(site.root), name])
        print(f"  {'ok ' if cp.returncode == 0 else 'FAILED'} {name}", flush=True)
        failed += cp.returncode != 0
    return 1 if failed else 0


def make_server(host: str = "127.0.0.1", port: int = 8000, root: str | Path = ".") -> ThreadingHTTPServer:
    handler = type("TraceLensHandler", (Handler,), {"site": Site(root)})
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = "127.0.0.1", port: int = 8000, root: str | Path = ".") -> None:
    httpd = make_server(host, port, root)
    print(f"TraceLens {__version__} demo on http://{host}:{port}/ (root {Path(root).resolve()})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "render-one":
    render_one(sys.argv[2], sys.argv[3])
