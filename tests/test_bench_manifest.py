"""The real-bug benchmark manifest (research track R3) must stay well-formed."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"id", "project", "url", "buggy_commit", "fixed_commit", "files_sha256", "licence", "class_claimed_upstream",
            "symptom_oracle", "port_layer_lines", "status", "tool_frozen_before_driver", "exclusion_reason"}


def _bugs():
    return tomllib.loads((ROOT / "bench" / "manifest.toml").read_text(encoding="utf-8"))["bug"]


def test_every_entry_has_the_required_fields_and_a_valid_status():
    bugs = _bugs()
    assert len({b["id"] for b in bugs}) == len(bugs)
    for b in bugs:
        assert REQUIRED <= set(b), (b["id"], REQUIRED - set(b))
        assert b["status"] in {"candidate", "reproduced", "excluded"}, b["id"]


def test_an_excluded_entry_says_why_and_a_reproduced_one_names_its_symptom_oracle():
    for b in _bugs():
        if b["status"] == "excluded":
            assert b["exclusion_reason"], b["id"]
        if b["status"] == "reproduced":
            assert b["symptom_oracle"], b["id"]


def test_entries_worked_on_before_any_freeze_are_not_called_blind():
    """Case studies must say so: the flag is false until a freeze tag exists in docs/research/PROTOCOL.md."""
    for b in _bugs():
        if b["status"] == "reproduced":
            assert b["tool_frozen_before_driver"] is False, b["id"]
