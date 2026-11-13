"""QNX target automation: SSH access and trace capture (PLAN.md §4, phase P1)."""

from .capture import CaptureResult, capture
from .ssh import Target, TargetError

__all__ = ["CaptureResult", "Target", "TargetError", "capture"]
