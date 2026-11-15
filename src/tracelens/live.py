"""Live view of a running fix (`tracelens fix --watch`): a local page fed by Server-Sent Events.

The fix engine publishes each step to a ``LiveFeed``; a small local web server streams the feed to
the browser. A browser that connects late first receives everything so far. Standard library only.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

JS_PATH = Path(__file__).with_name("live.js")


def live_js() -> bytes:
    return JS_PATH.read_bytes()


class LiveFeed:
    def __init__(self):
        self.events: list[dict] = []
        self._cond = threading.Condition()

    def publish(self, evt: dict) -> None:
        with self._cond:
            self.events.append(evt)
            self._cond.notify_all()

    def wait(self, index: int, timeout: float) -> list[dict]:
        """Events from ``index`` on; blocks up to ``timeout`` seconds when there are none yet."""
        with self._cond:
            if index >= len(self.events):
                self._cond.wait(timeout)
            return self.events[index:]


def make_live_server(feed: LiveFeed, host: str = "127.0.0.1", port: int = 8777,
                     title: str = "Live fix") -> ThreadingHTTPServer:
    from . import app

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/live.js":
                return self._send(live_js(), "text/javascript; charset=utf-8")
            if path == "/events":
                return self._stream()
            if path in ("/", "/live"):
                return self._send(app.live_page("live", "/events", title), "text/html; charset=utf-8")
            self.send_error(404)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            i = 0
            try:
                while True:
                    new = feed.wait(i, 15.0)
                    if not new:
                        self.wfile.write(b": still working\n\n")  # keep the connection alive
                    for evt in new:
                        self.wfile.write(b"data: " + json.dumps(evt).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                    i += len(new)
                    if any(e.get("type") == "done" for e in new):
                        return
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    return ThreadingHTTPServer((host, port), Handler)


def start_live_view(feed: LiveFeed, port: int = 8777, title: str = "Live fix", open_browser: bool = True) -> str:
    """Serve the live view in a background thread; returns its URL."""
    httpd = make_live_server(feed, "127.0.0.1", port, title)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return url
