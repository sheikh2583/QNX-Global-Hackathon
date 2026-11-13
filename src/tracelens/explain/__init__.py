"""AI explanations of findings, with citations validated against the trace (PLAN.md §7)."""

from .citations import validate
from .evidence import EvidencePack, build_pack, format_pack

__all__ = ["EvidencePack", "build_pack", "format_pack", "validate"]
