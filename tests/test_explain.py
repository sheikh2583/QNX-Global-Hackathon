"""Explain pipeline tests with a scripted fake Claude client (no network, no API key)."""

import json
from types import SimpleNamespace

import pytest

from tracelens.analyze import analyze_text
from tracelens.explain.citations import cited_ids, validate
from tracelens.explain.claude import Explainer
from tracelens.explain.evidence import build_pack, format_pack
from tracelens.explain.prompts import SCHEMA
from tracelens.report.html import render
from tracelens.report.json_out import to_dict
from tracelens.testing import scenarios as S


class FakeClient:
    """Mimics client.beta.messages.create; returns scripted replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, str):  # stop_reason shortcut
            return SimpleNamespace(stop_reason=reply, content=[], model=kwargs["model"])
        return SimpleNamespace(stop_reason="end_turn", model=kwargs["model"],
                               content=[SimpleNamespace(type="text", text=json.dumps(reply))])


def expl(evidence_ids, text_extra=""):
    return {
        "headline": "control starves behind telemetry while logger holds the semaphore" + text_extra,
        "causal_chain": [{"text": "logger takes the buffer semaphore.", "evidence": evidence_ids}],
        "qnx_mechanism": "Semaphores have no owner, so no priority inheritance.",
        "impact": "control misses its 1 ms budget.",
        "fix": {"summary": "Use a PTHREAD_PRIO_INHERIT mutex.", "steps": ["Replace sem_t with pthread_mutex_t."]},
        "confidence": "high",
    }


@pytest.fixture(scope="module")
def z1():
    import tomllib
    from tracelens.config import Config, Deadline
    c = Config()
    for name, d in tomllib.loads(S.DEADLINES_TOML)["deadlines"].items():
        c.deadlines[name] = Deadline(**d)
    a = analyze_text(S.z1_prio_inversion(), c)
    assert a.findings
    return a


def test_evidence_pack_marks_core_events_and_adds_context(z1):
    f = z1.findings[0]
    pack = build_pack(z1.model, f)
    assert pack.core_ids == set(f.evidence)
    assert pack.allowed_ids > pack.core_ids  # context was added
    text = format_pack(z1.model, pack)
    for eid in f.evidence:
        assert f"*[E{eid}]" in text


def test_validator_rules():
    allowed, core = {1, 2, 3}, {2}
    assert validate(expl([2]), allowed, core) == []
    assert any("not in the evidence" in p for p in validate(expl([2, 99]), allowed, core))
    assert any("not in the evidence" in p for p in validate(expl([2], " (see E77)"), allowed, core))
    assert any("none of the detector" in p for p in validate(expl([1]), allowed, core))
    bad = expl([2]); bad["causal_chain"].append({"text": "uncited claim", "evidence": []})
    assert any("cites no events" in p for p in validate(bad, allowed, core))
    assert cited_ids(expl([2], " E3")) == {2, 3}


def test_verified_first_try_and_cached(z1, tmp_path):
    f = z1.findings[0]
    client = FakeClient([expl([f.evidence[0]])])
    ex = Explainer(client=client, cache_dir=tmp_path)
    x = ex.explain(z1, f)
    assert x.verified and x.attempts == 1 and not x.cached
    # Request shape: structured output, cached system prompt, fallbacks, explicit effort.
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert call["output_config"]["effort"] == "medium"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["fallbacks"] == "default"
    # Second run: served from disk, no API call.
    again = Explainer(client=FakeClient([]), cache_dir=tmp_path).explain(z1, f)
    assert again.cached and again.verified and again.data == x.data


def test_hallucinated_citation_is_corrected_by_retry(z1):
    f = z1.findings[0]
    client = FakeClient([expl([f.evidence[0], 987654]), expl([f.evidence[0]])])
    x = Explainer(client=client, cache_dir=None).explain(z1, f)
    assert x.verified and x.attempts == 2
    retry_msg = client.calls[1]["messages"][-1]["content"]
    assert "E987654" in retry_msg


def test_persistent_hallucination_is_flagged_not_hidden(z1):
    f = z1.findings[0]
    client = FakeClient([expl([987654]), expl([987654])])
    x = Explainer(client=client, cache_dir=None).explain(z1, f)
    assert not x.verified and x.attempts == 2
    assert any("E987654" in p for p in x.problems)
    html = render(z1, {f.id: x})
    assert "citations NOT verified" in html


def test_refusal_is_reported(z1):
    f = z1.findings[0]
    x = Explainer(client=FakeClient(["refusal"]), cache_dir=None).explain(z1, f)
    assert x.data is None and "declined" in x.error


def test_reports_carry_explanations_and_link_citations(z1):
    f = z1.findings[0]
    pack = build_pack(z1.model, f)
    context_id = sorted(pack.allowed_ids - pack.core_ids)[0]
    client = FakeClient([expl([f.evidence[0], context_id])])
    x = Explainer(client=client, cache_dir=None).explain(z1, f)
    assert x.verified
    html = render(z1, {f.id: x})
    assert "citations verified" in html
    assert f'href="#{f.id}-E{context_id}"' in html and f'id="{f.id}-E{context_id}"' in html
    d = to_dict(z1, {f.id: x})
    assert d["findings"][0]["explanation"]["verified"] is True
