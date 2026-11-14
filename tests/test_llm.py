"""Provider layer: Gemini over HTTPS (faked here, no network) and provider selection."""

import json

import pytest

from tracelens.analyze import analyze_text
from tracelens.config import Config
from tracelens.explain.claude import Explainer
from tracelens.llm import GeminiLLM, LLMError, pick_provider, rank_gemini_models
from tracelens.testing import scenarios as S

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def _ok(obj, model="gemini-x-pro-001", finish="STOP", thought=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": json.dumps(obj)}]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "modelVersion": model}


class FakeHTTP:
    def __init__(self, replies, models=None):
        self.replies, self.calls, self.sleeps = list(replies), [], []
        self.models = models or ["models/gemini-2.5-pro"]

    def post(self, url, headers, body):
        self.calls.append((url, headers, json.loads(json.dumps(body))))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, url, headers):
        return {"models": [{"name": n, "supportedGenerationMethods": ["generateContent"]} for n in self.models]}


def _err(status, text="", retry=None):
    e = LLMError(f"Gemini API HTTP {status}: {text}")
    e.status, e.retry_after = status, retry
    return e


def _llm(http, **kw):
    return GeminiLLM(api_key="test-key", post=http.post, get=http.get, sleep=http.sleeps.append, **kw)


def test_request_shape_and_reply():
    http = FakeHTTP([_ok({"a": "x"}, thought="thinking...")])
    llm = _llm(http, model="gemini-2.5-pro")
    r = llm.json_call("SYS", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "{}"},
                              {"role": "user", "content": "again"}], SCHEMA)
    assert r.stop == "ok" and json.loads(r.text) == {"a": "x"} and r.model == "gemini-x-pro-001"
    url, headers, body = http.calls[0]
    assert url.endswith("/models/gemini-2.5-pro:generateContent")
    assert headers["x-goog-api-key"] == "test-key" and "key=" not in url  # key in a header, not the URL
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_best_model_is_picked_from_what_the_key_can_use():
    names = ["models/gemini-2.5-flash", "models/gemini-2.5-pro", "models/gemini-3.5-flash",
             "models/gemini-3.6-pro-preview-09-2026", "models/gemini-embedding-001",
             "models/gemini-2.5-flash-preview-tts", "models/gemini-3.5-flash-lite", "models/gemma-3-27b-it"]
    ranked = rank_gemini_models(names)
    assert ranked[0] == "gemini-3.5-flash"  # newest stable beats an older stable pro and any preview
    assert "gemini-embedding-001" not in ranked and not any("tts" in n or "gemma" in n for n in ranked)
    assert ranked.index("gemini-2.5-pro") < ranked.index("gemini-2.5-flash")
    assert _llm(FakeHTTP([], models=names)).model == "gemini-3.5-flash"


def test_rate_limits_are_retried_with_the_servers_delay():
    http = FakeHTTP([_err(429, "quota", retry=7.0), _err(503), _ok({"a": "y"})])
    r = _llm(http, model="gemini-2.5-pro").json_call("S", [{"role": "user", "content": "q"}], SCHEMA)
    assert r.stop == "ok" and http.sleeps == [7.0, 10.0]


def test_schema_rejection_falls_back_to_json_mode_with_schema_in_prompt():
    http = FakeHTTP([_err(400, "Invalid JSON payload: unknown field responseJsonSchema"), _ok({"a": "z"})])
    llm = _llm(http, model="gemini-2.5-pro")
    assert llm.json_call("S", [{"role": "user", "content": "q"}], SCHEMA).stop == "ok"
    body = http.calls[1][2]
    assert "responseJsonSchema" not in body["generationConfig"]
    assert "JSON Schema" in body["systemInstruction"]["parts"][-1]["text"]
    assert llm.schema_mode == "prompt"


def test_finish_reasons_map_to_stops():
    for finish, stop in (("MAX_TOKENS", "max_tokens"), ("SAFETY", "refusal"), ("RECITATION", "refusal")):
        http = FakeHTTP([_ok({"a": "x"}, finish=finish)])
        assert _llm(http, model="m").json_call("S", [{"role": "user", "content": "q"}], SCHEMA).stop == stop
    http = FakeHTTP([{"promptFeedback": {"blockReason": "SAFETY"}}])
    assert _llm(http, model="m").json_call("S", [{"role": "user", "content": "q"}], SCHEMA).stop == "refusal"


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiLLM(model="m")


def test_provider_follows_the_key_that_is_set(monkeypatch):
    for k in ("TRACELENS_LLM", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert pick_provider() == "gemini"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert pick_provider() == "claude" and pick_provider("gemini") == "gemini"
    monkeypatch.setenv("TRACELENS_LLM", "gemini")
    assert pick_provider() == "gemini"


def test_explainer_runs_on_gemini_with_checked_citations():
    """Same validator, same retry: a wrong citation from Gemini is caught and corrected."""
    a = analyze_text(S.z1_prio_inversion(), Config())
    f = a.findings[0]
    m = a.model
    eid = next(i for i in f.evidence if m.by_id[i].key is not None)
    e = m.by_id[eid]

    def expl(observed):
        return {"headline": "control starves behind telemetry",
                "causal_chain": [{"text": "logger takes the semaphore.",
                                  "evidence": [{"event": eid, "thread": m.label(e.key), "observed": observed}]}],
                "qnx_mechanism": "Semaphores have no owner.", "impact": "control misses its budget.",
                "fix": {"summary": "Use a mutex.", "steps": ["Replace sem_t."]}, "confidence": "high"}

    http = FakeHTTP([_ok(expl("IRQ")), _ok(expl(e.kind))])
    x = Explainer(llm=_llm(http, model="gemini-2.5-pro"), cache_dir=None).explain(a, f)
    assert x.verified and x.attempts == 2 and x.model == "gemini-x-pro-001"
    retry = http.calls[1][2]["contents"]
    assert [c["role"] for c in retry] == ["user", "model", "user"] and "IRQ" in retry[-1]["parts"][0]["text"]
