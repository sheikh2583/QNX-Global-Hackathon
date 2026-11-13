from __future__ import annotations

import math


def us(ns: float) -> float:
    return ns / 1000.0


def ms(ns: float) -> float:
    return ns / 1_000_000.0


def fmt_ms(ns: float) -> str:
    return f"{ms(ns):.2f} ms"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(p / 100.0 * len(s)) - 1))
    return s[k]
