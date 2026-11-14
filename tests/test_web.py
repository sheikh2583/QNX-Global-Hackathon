"""The hosted demo (`tracelens serve`), exercised over real HTTP on a random port."""

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
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
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


def test_landing_shows_real_results_and_the_live_panel(base):
    code, html = get(base + "/")
    assert code == 200 and "<title>TraceLens on QNX 8.0</title>" in html
    assert "Try it live" in html and 'href="/remedy/z1_infusion_pump"' in html and 'action="/upload"' in html
    assert html.count('<svg class="tl"') == 4  # the recorded before/after timelines
    assert get(base + "/healthz") == (200, "ok\n")


def test_live_analysis_of_a_real_qnx_trace(base):
    code, html = get(base + "/trace/z1_infusion_pump")
    assert code == 200 and "Priority inversion: control waited on logger via a semaphore" in html
    assert 'href="/remedy/z1_infusion_pump"' in html  # the bar links to the next step


def test_live_fix_planning_produces_the_patch(base):
    code, html = get(base + "/remedy/z1_infusion_pump")
    assert code == 200 and "automatic" in html and "PTHREAD_PRIO_INHERIT" in html
    assert "pthread_mutex_lock(&amp;buf_lock)" in html  # the diff, escaped


def test_recorded_proof_from_the_qnx_vm(base):
    code, html = get(base + "/fix/z5_motor_encoder")
    assert code == 200 and "VERIFIED" in html and "TraceLens" in html


def test_unknown_paths_and_traversal_are_404(base):
    for p in ("/trace/../../pyproject.toml", "/trace/nope", "/fix/..%2f..%2fREADME.md", "/remedy/z1_infusion_pump_fixed"):
        assert get(base + p)[0] == 404, p


def test_upload_a_trace_with_source_gets_findings_and_a_patch(base):
    src = (ROOT / "bugzoo" / "z1_infusion_pump" / "main.c").read_bytes()
    code, html = post(base + "/upload", {"trace": ("z1.txt", S.z1_prio_inversion().encode()),
                                          "source": ("main.c", src)})
    assert code == 200 and "pthread_mutex_lock(&amp;buf_lock)" in html


def test_upload_without_source_gets_the_report(base):
    code, html = post(base + "/upload", {"trace": ("z3.txt", S.z3_ipc_deadlock().encode())})
    assert code == 200 and "fusion" in html.lower() and "deadlock" in html.lower()


def test_bad_uploads_are_rejected_clearly(base):
    code, html = post(base + "/upload", {"trace": ("x.txt", b"not a trace at all")})
    assert code == 400 and "Could not analyze" in html
    code, _ = post(base + "/upload", {"other": ("x.txt", b"x")})
    assert code == 400


def test_prebuilt_pages_are_served_without_analyzing(tmp_path):
    """On a 512 MB host the committed traces are rendered at deploy time; the server just reads files."""
    import shutil
    from tracelens.web import Site, render_one
    root = tmp_path / "repo"
    (root / "fixtures" / "real").mkdir(parents=True)
    for f in ("tracelens.toml", "z1_infusion_pump.txt.gz"):
        shutil.copy(ROOT / "fixtures" / "real" / f, root / "fixtures" / "real" / f)
    shutil.copytree(ROOT / "bugzoo" / "z1_infusion_pump", root / "bugzoo" / "z1_infusion_pump")
    render_one(root, "z1_infusion_pump")
    page = root / ".site" / "trace" / "z1_infusion_pump.html"
    assert page.exists() and (root / ".site" / "remedy" / "z1_infusion_pump.html").exists()
    page.write_bytes(page.read_bytes().replace(b"Priority inversion", b"PREBUILT-MARK", 1))

    httpd = make_server("127.0.0.1", 0, root)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        code, html = get(f"http://127.0.0.1:{httpd.server_address[1]}/trace/z1_infusion_pump")
        assert code == 200 and "PREBUILT-MARK" in html  # served from .site, not recomputed
        assert not Site(root)._cache
    finally:
        httpd.shutdown()
        httpd.server_close()
