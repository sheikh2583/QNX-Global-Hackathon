"""Thresholds and deadline declarations, loaded from ``tracelens.toml``.

Example::

    [thresholds]
    inversion_min_block_us = 1000

    [deadlines.control]     # thread name (from TL_META) -> timing budget
    budget_us = 1000
    period_us = 10000

    fail_on = "high"        # CI exits non-zero at or above this severity
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Deadline:
    budget_us: float
    period_us: float | None = None


@dataclass
class Thresholds:
    inversion_min_block_us: float = 1000
    inversion_min_interference_us: float = 500
    contention_min_total_wait_us: float = 2000
    contention_min_waits: int = 5
    irq_max_latency_us: float = 200
    irq_max_handler_us: float = 500
    deadlock_min_blocked_us: float = 50_000
    chain_min_depth: int = 3


@dataclass
class Config:
    thresholds: Thresholds = field(default_factory=Thresholds)
    deadlines: dict[str, Deadline] = field(default_factory=dict)
    fail_on: str = "high"


def load_config(path: str | Path | None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    known = {f.name for f in fields(Thresholds)}
    for k, v in data.get("thresholds", {}).items():
        if k in known:
            setattr(cfg.thresholds, k, v)
    for name, d in data.get("deadlines", {}).items():
        cfg.deadlines[name] = Deadline(budget_us=d["budget_us"], period_us=d.get("period_us"))
    if "fail_on" in data:
        cfg.fail_on = data["fail_on"]
    return cfg
