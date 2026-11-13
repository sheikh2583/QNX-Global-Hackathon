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


def union_ns(spans) -> int:
    """Total length of the union of (start, end, ...) spans: overlapping time counts once."""
    total, cur_s, cur_e = 0, None, None
    for span in sorted(spans):
        s, e = span[0], span[1]
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def intersect(a, b) -> list[tuple[int, int]]:
    """Intersection of two lists of (start, end, ...) spans."""
    out = []
    for s1, e1, *_ in a:
        for s2, e2, *_ in b:
            s, e = max(s1, s2), min(e1, e2)
            if s < e:
                out.append((s, e))
    return out
