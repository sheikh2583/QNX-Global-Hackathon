"""research/make_numbers.py: the numbers a paper quotes must come from committed data and stay in step with it."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _module():
    spec = importlib.util.spec_from_file_location("make_numbers", ROOT / "research" / "make_numbers.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_numbers"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_committed_numbers_match_a_fresh_run():
    m = _module()
    n = m.numbers()
    assert (ROOT / "docs" / "research" / "numbers.json").read_text(encoding="utf-8") == \
        __import__("json").dumps(n, indent=1, sort_keys=True) + "\n", "run: python research/make_numbers.py"
    assert (ROOT / "docs" / "research" / "numbers.tex").read_text(encoding="utf-8") == m.render_tex(n)


def test_the_residual_bounds_are_the_ones_the_docs_quote():
    n = _module().numbers()
    assert n["ResidualZeroOfFive"] == "45.1\\%" and n["ResidualZeroOfTen"] == "25.9\\%"
    assert n["ResidualZeroOfTwenty"] == "13.9\\%" and n["RunsNeededTenPercent"] == "29"


def test_case_studies_are_not_counted_as_blind_results():
    n = _module().numbers()
    # reproduced entries worked on before a freeze are case studies; BenchBlind counts only frozen-first entries
    assert int(n["BenchReproduced"]) >= 3
    # the blind attempts so far all failed to reproduce; if one ever does, update this on purpose
    assert n["BenchBlindAttempted"] == "3" and n["BenchBlindReproduced"] == "0"
