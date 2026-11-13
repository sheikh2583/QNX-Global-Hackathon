"""TraceLens as an MCP server, so AI assistants can query QNX traces.

Register with Claude Code::

    claude mcp add tracelens -- tracelens mcp

Then ask, for example, "why did control miss its deadline in captures/z1.txt?".
The assistant calls these tools; every answer is grounded in detector output and
event IDs from the trace. Requires the ``mcp`` extra (``pip install tracelens[mcp]``).
"""

from __future__ import annotations

import json

from . import service

INSTRUCTIONS = (
    "TraceLens analyzes QNX Neutrino kernel event traces (traceprinter text). Start with analyze_trace "
    "on a trace file, then get_finding for evidence, list_threads / thread_states / events to dig in, "
    "and compare_traces to judge a fix over several before/after captures. Cite event IDs from the "
    "results when explaining; never infer a bug the detectors did not report without saying so."
)


def build_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("tracelens", instructions=INSTRUCTIONS)

    def js(data) -> str:
        return json.dumps(data, indent=1, default=str)

    @server.tool()
    def analyze_trace(trace_path: str, config_path: str | None = None) -> str:
        """Run every TraceLens detector on a traceprinter text file; returns findings with severity,
        summary and metrics, plus trace integrity notes. config_path: optional tracelens.toml."""
        return js(service.analyze_trace(trace_path, config_path))

    @server.tool()
    def get_finding(trace_path: str, finding_id: str, config_path: str | None = None) -> str:
        """Full detail for one finding (e.g. TL-001): metrics, QNX note, and its evidence events
        with source line numbers and raw trace text."""
        return js(service.get_finding(trace_path, finding_id, config_path))

    @server.tool()
    def list_threads(trace_path: str) -> str:
        """Threads in the trace with base priority, priority changes, CPUs, and % of time running,
        ready (preempted) and blocked."""
        return js(service.list_threads(trace_path))

    @server.tool()
    def thread_states(trace_path: str, thread: str, start_ms: float = 0, end_ms: float | None = None) -> str:
        """State intervals (RUNNING, READY, SEM, MUTEX, SEND, REPLY, INTR...) of one thread within a
        time window in ms from trace start. thread: a name from list_threads or 'pid/tid'."""
        return js(service.thread_states(trace_path, thread, start_ms, end_ms))

    @server.tool()
    def events(trace_path: str, start_ms: float = 0, end_ms: float | None = None, thread: str | None = None,
               event_class: str | None = None, limit: int = 100) -> str:
        """Raw kernel events in a time window, optionally for one thread or one class
        (THREAD, KER_CALL, KER_EXIT, INT_ENTR, USREVENT...). Max 200 rows."""
        return js(service.events(trace_path, start_ms, end_ms, thread, event_class, limit))

    @server.tool()
    def compare_traces(before: list[str], after: list[str], config_path: str | None = None,
                       min_runs: int = 5) -> str:
        """Before/after verdict over several captures: VERIFIED, NOT FIXED or INCONCLUSIVE, with
        finding rates and per-deadline p99 comparison (Mann-Whitney U)."""
        return js(service.compare_traces(before, after, config_path, min_runs))

    return server


def main() -> None:
    build_server().run("stdio")
