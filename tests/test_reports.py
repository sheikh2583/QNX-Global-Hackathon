"""Perfetto export, SARIF and HTML reports."""

import json

import pytest

from tracelens.analyze import analyze_text
from tracelens.cli import main
from tracelens.export.perfetto import FINDINGS_PID, to_chrome_trace
from tracelens.testing import scenarios as S


@pytest.fixture
def z1(tmp_path):
    p = tmp_path / "z1.txt"
    p.write_text(S.z1_prio_inversion(), encoding="utf-8")
    c = tmp_path / "t.toml"
    c.write_text(S.DEADLINES_TOML, encoding="utf-8")
    return str(p), str(c)


def test_perfetto_trace_has_states_markers_and_findings(z1):
    trace, conf = z1
    from tracelens.analyze import analyze_file
    from tracelens.config import load_config
    d = to_chrome_trace(analyze_file(trace, load_config(conf)))
    evs = d["traceEvents"]
    states = [e for e in evs if e.get("cat") == "state"]
    assert states and all(e["dur"] > 0 and e["ts"] >= 0 for e in states)
    assert {"RUNNING", "READY", "SEM"} <= {e["name"] for e in states}
    assert any(e.get("cat") == "marker" and e["name"].startswith("TL_JOB_START") for e in evs)
    findings = [e for e in evs if e.get("cat") == "finding"]
    assert len(findings) == 2 and all(e["pid"] == FINDINGS_PID for e in findings)
    assert findings[0]["args"]["evidence_events"]
    names = {e["args"]["name"] for e in evs if e["ph"] == "M"}
    assert "TraceLens findings" in names and any("control" in n for n in names)


def test_export_cli_writes_json(z1, tmp_path):
    trace, conf = z1
    out = tmp_path / "z1.perfetto.json"
    assert main(["export", trace, "-c", conf, "-o", str(out), "--no-calls"]) == 0
    d = json.loads(out.read_text())
    assert not any(e.get("cat") == "kernel_call" for e in d["traceEvents"])


def test_sarif_results_point_at_trace_lines(z1, tmp_path):
    trace, conf = z1
    out = tmp_path / "z1.sarif"
    assert main(["analyze", trace, "-c", conf, "-q", "--sarif", str(out)]) == 1
    d = json.loads(out.read_text())
    assert d["version"] == "2.1.0"
    run = d["runs"][0]
    assert {r["id"] for r in run["tool"]["driver"]["rules"]} == {"priority_inversion", "deadline_miss"}
    res = run["results"][0]
    assert res["level"] == "error" and res["locations"][0]["physicalLocation"]["region"]["startLine"] > 1
    assert res["partialFingerprints"]["tracelensFinding"].startswith("priority_inversion:")


def test_html_report_flags_lossy_traces():
    from tracelens.report.html import render
    text = ("TRACEPRINTER\n -- HEADER FILE INFORMATION --\n  CYCLES_PER_SEC:: 1000000000\n -- KERNEL EVENTS --\n"
            "t:0x00000010 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
            "t:0x00000020 CPU:01 THREAD  :THRUNNING pid:1 tid:1\n")
    html = render(analyze_text(text))
    assert "Lossy trace: verdict withheld" in html and "two CPUs" in html
    assert "Lossy trace" not in render(analyze_text(S.z0_clean()))
