"""research/make_numbers.py: the numbers a paper quotes must come from committed data and stay in step with it."""

import importlib.util
import json
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
    on_disk = json.loads((ROOT / "docs" / "research" / "numbers.json").read_text(encoding="utf-8"))
    n.pop("LinesOfCode"), on_disk.pop("LinesOfCode")  # follows every edit of src/; regenerate when building the paper
    assert on_disk == n, "run: python research/make_numbers.py"
    tex = (ROOT / "docs" / "research" / "numbers.tex").read_text(encoding="utf-8")
    assert all((chr(92) + "tl" + k + "}") in tex for k in n)


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
