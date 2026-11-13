"""Trace ingestion: turn QNX trace output into normalized :class:`tracelens.events.Event` streams."""

from .traceprinter import ParsedTrace, TraceFormatError, parse_file, parse_text

__all__ = ["ParsedTrace", "TraceFormatError", "parse_file", "parse_text"]
