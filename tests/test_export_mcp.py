"""Perfetto export, the query service, and the MCP server wiring."""

import asyncio
import json

import pytest

from tracelens import service
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


def test_service_queries(z1):
    trace, conf = z1
    s = service.analyze_trace(trace, conf)
    assert [f["kind"] for f in s["findings"]] == ["priority_inversion", "deadline_miss"] and not s["lossy"]
    f = service.get_finding(trace, "TL-001", conf)
    assert f["evidence"] and all("raw" in e and e["line"] > 0 for e in f["evidence"])
    threads = {t["thread"]: t for t in service.list_threads(trace)}
    assert threads["control"]["base_prio"] == 50 and threads["telemetry"]["running_pct"] > 50
    states = service.thread_states(trace, "control", 0, 5)
    assert states and {"state", "start_ms", "dur_ms"} <= set(states[0])
    evs = service.events(trace, thread="logger", event_class="KER_CALL")
    assert evs and all(e["class"] == "KER_CALL" and e["thread"] == "logger" for e in evs)
    with pytest.raises(KeyError):
        service.get_finding(trace, "TL-999", conf)


def test_mcp_server_lists_and_calls_tools(z1):
    pytest.importorskip("mcp.server.mcpserver")
    from tracelens.mcp_server import build_server
    trace, conf = z1
    server = build_server()

    async def go():
        tools = await server.list_tools()
        result = await server.call_tool("analyze_trace", {"trace_path": trace, "config_path": conf})
        return tools, result

    tools, result = asyncio.run(go())
    assert {t.name for t in tools} == {"analyze_trace", "get_finding", "list_threads", "thread_states",
                                       "events", "compare_traces"}
    text = json.dumps(result, default=str)
    assert "priority_inversion" in text
