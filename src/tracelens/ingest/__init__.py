"""Trace ingestion: turn QNX trace output into normalized :class:`tracelens.events.Event` streams."""

from .traceprinter import ParsedTrace, parse_file, parse_text

__all__ = ["ParsedTrace", "parse_file", "parse_text"]
