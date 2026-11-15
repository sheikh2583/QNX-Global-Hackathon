"""The TraceLens web app (`tracelens serve`), exercised over real HTTP on a random port."""

import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from tracelens.testing import scenarios as S
from tracelens.web import make_server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def base():
    httpd = make_server("127.0.0.1", 0, ROOT)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def post(url, fields):
    boundary = uuid.uuid4().hex
    body = b""
    for name, (filename, data) in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_home_explains_the_product_and_shows_measured_proof(base):
    code, html = get(base + "/")
    assert code == 200 and "Analyze your trace" in html and 'href="/demo"' in html
    assert "Three steps" in html and '<svg class="chart"' in html  # before/after chart from docs/results
    assert "4 of 5" in html
    assert get(base + "/healthz") == (200, "ok\n")


def test_guided_demo_walks_one_real_trace_from_bug_to_proof(base):
    code, html = get(base + "/demo")
    assert code == 200
    for step in ("program", "recording", "found", "fix", "proof", "reliable", "try"):
        assert f'id={step}' in html, step
    assert "SYNC_SEM_WAIT" in html  # real kernel events from the recording
    assert "A high-priority task was held up by lower-priority work" in html
    assert "Not fixed yet" in html and "Verified" in html  # round 1, round 2
    assert html.count('<svg class="tl"') >= 4  # per-problem moments + before/after


def test_example_report_is_plain_language_with_a_patch(base):
    code, html = get(base + "/example/z1_infusion_pump")
    assert code == 200 and "Fixed automatically" in html and "Download the patch" in html
    assert "pthread_mutex_lock(&amp;buf_lock)" in html
    assert "TRACE INTEGRITY" not in html and "detector error" not in html


def test_engineers_view_and_proof_are_still_there(base):
    code, html = get(base + "/trace/z1_infusion_pump")
    assert code == 200 and "Priority inversion: control waited on logger via a semaphore" in html
    code, html = get(base + "/proof/z5_motor_encoder")
    assert code == 200 and "VERIFIED" in html
    code, html = get(base + "/remedy/z1_infusion_pump")  # old link, redirected
    assert code == 200 and "Download the patch" in html


def test_static_pages(base):
    for path, text in (("/analyze", "How to record"), ("/guide", "How to read a TraceLens report"),
                       ("/examples", "Five real QNX programs")):
        code, html = get(base + path)
        assert code == 200 and text in html, path


def test_unknown_paths_and_traversal_are_404(base):
    for p in ("/trace/../../pyproject.toml", "/trace/nope", "/proof/..%2f..%2fREADME.md", "/example/z1_infusion_pump_fixed"):
        assert get(base + p)[0] == 404, p


def test_upload_with_source_gets_a_report_and_a_patch(base):
    src = (ROOT / "bugzoo" / "z1_infusion_pump" / "main.c").read_bytes()
    code, html = post(base + "/analyze", {"trace": ("z1.txt", S.z1_prio_inversion().encode()),
                                           "source": ("main.c", src)})
    assert code == 200 and "Your patch" in html and "pthread_mutex_lock(&amp;buf_lock)" in html


def test_upload_without_source_gets_plain_findings(base):
    code, html = post(base + "/upload", {"trace": ("z3.txt", S.z3_ipc_deadlock().encode())})
    assert code == 200 and "Two parts of the program are waiting for each other" in html


def test_bad_uploads_are_explained(base):
    code, html = post(base + "/analyze", {"trace": ("x.txt", b"not a trace at all")})
    assert code == 400 and "could not be analyzed" in html and "traceprinter" in html
    code, _ = post(base + "/analyze", {"other": ("x.txt", b"x")})
    assert code == 400


def test_prebuilt_pages_are_served_without_analyzing(tmp_path):
    """On a 512 MB host the trace pages are rendered at deploy time; the server just reads files."""
    import shutil
    from tracelens.web import render_one
    root = tmp_path / "repo"
    (root / "fixtures" / "real").mkdir(parents=True)
    for f in ("tracelens.toml", "z1_infusion_pump.txt.gz"):
        shutil.copy(ROOT / "fixtures" / "real" / f, root / "fixtures" / "real" / f)
    shutil.copytree(ROOT / "bugzoo" / "z1_infusion_pump", root / "bugzoo" / "z1_infusion_pump")
    render_one(root, "z1_infusion_pump")
    for rel in ("trace/z1_infusion_pump.html", "example/z1_infusion_pump.html", "demo.html"):
        assert (root / ".site" / rel).exists(), rel
    page = root / ".site" / "example" / "z1_infusion_pump.html"
    page.write_bytes(page.read_bytes().replace(b"what went wrong", b"PREBUILT-MARK", 1))

    httpd = make_server("127.0.0.1", 0, root)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        code, html = get(f"http://127.0.0.1:{httpd.server_address[1]}/example/z1_infusion_pump")
        assert code == 200 and "PREBUILT-MARK" in html  # served from .site, not recomputed
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_live_view_streams_the_fix_as_it_happens():
    import json
    from tracelens.live import LiveFeed, make_live_server
    feed = LiveFeed()
    httpd = make_live_server(feed, "127.0.0.1", 0, "Fixing test")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, html = get(base + "/")
        assert code == 200 and 'data-mode="live"' in html and '<script src="/live.js"' in html
        assert "TraceLens live fix view" in get(base + "/live.js")[1]
        feed.publish({"type": "start", "workload": "w", "runs": 5, "max_rounds": 3, "files": {}})
        threading.Timer(0.3, feed.publish, args=[{"type": "done", "status": "VERIFIED", "rounds": 1}]).start()
        with urllib.request.urlopen(base + "/events", timeout=30) as r:
            body = r.read().decode()  # ends after the done event
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        assert [e["type"] for e in events] == ["start", "done"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_recorded_fix_is_replayed(tmp_path):
    import json
    root = tmp_path / "repo"
    b = root / "docs" / "results" / "fixes" / "z1_infusion_pump"
    b.mkdir(parents=True)
    (b / "events.jsonl").write_text('{"type": "start", "t": 1}\n{"type": "done", "t": 2, "status": "VERIFIED"}\n')
    httpd = make_server("127.0.0.1", 0, root)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, html = get(base + "/replay/z1_infusion_pump")
        assert code == 200 and 'data-mode="replay"' in html and "/replay/z1_infusion_pump/events.json" in html
        code, body = get(base + "/replay/z1_infusion_pump/events.json")
        assert code == 200 and [e["type"] for e in json.loads(body)] == ["start", "done"]
        assert get(base + "/replay/nope")[0] == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
