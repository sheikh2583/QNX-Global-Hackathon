"""One small interface over the language models TraceLens can use for explain and fix.

Detection never touches a model. Explanations and patches do, and both only need one thing:
"given a system prompt and a conversation, return JSON matching this schema". Two providers:

``claude``  Anthropic SDK (optional extra ``tracelens[ai]``), structured outputs, server-side fallbacks.
``gemini``  Google Gemini API over plain HTTPS (stdlib only), JSON-schema response mode.

Pick with ``--provider`` / ``TRACELENS_LLM``; by default whichever key is set wins
(``ANTHROPIC_API_KEY``, else ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``). Keys are read from the
environment only and never logged.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"


@dataclass
class Reply:
    text: str
    stop: str  # "ok" | "refusal" | "max_tokens"
    model: str


class LLMError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- Claude
class ClaudeLLM:
    provider = "claude"

    def __init__(self, model: str | None = None, effort: str = "medium", client: Any | None = None):
        if client is None:
            import anthropic  # optional dependency
            client = anthropic.Anthropic()
        self.client, self.model, self.effort = client, model or CLAUDE_MODEL, effort

    def json_call(self, system: str, messages: list[dict[str, str]], schema: dict) -> Reply:
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=[CLAUDE_FALLBACK_BETA],
            fallbacks="default",  # re-run on a fallback model if the request is declined
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=list(messages),
        )
        stop = {"refusal": "refusal", "max_tokens": "max_tokens"}.get(resp.stop_reason, "ok")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return Reply(text=text, stop=stop, model=getattr(resp, "model", self.model))


# ----------------------------------------------------------------------------- Gemini
Post = Callable[[str, dict, dict], dict]  # (url, headers, body) -> parsed JSON; raises LLMError(status)


def _http(url: str, headers: dict, body: dict | None, timeout: float = 300) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        err = LLMError(f"Gemini API HTTP {e.code}: {detail}")
        err.status = e.code  # type: ignore[attr-defined]
        err.retry_after = _retry_after(e.headers.get("Retry-After"), detail)  # type: ignore[attr-defined]
        raise err from None


def _retry_after(header: str | None, detail: str) -> float | None:
    if header and header.strip().isdigit():
        return float(header)
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', detail)
    return float(m.group(1)) if m else None


_SKIP = ("embedding", "tts", "image", "audio", "live", "robotics", "computer-use", "aqa", "learnlm",
         "gemma", "veo", "imagen", "native")


def rank_gemini_models(names: list[str]) -> list[str]:
    """Best first: stable over preview/exp, newest version, pro > flash > flash-lite."""
    def key(name: str):
        n = name.removeprefix("models/")
        m = re.match(r"gemini-(\d+(?:\.\d+)?)-(pro|flash-lite|flash)(.*)$", n)
        if not m:
            return None
        version, tier, rest = float(m.group(1)), m.group(2), m.group(3)
        if any(s in n for s in _SKIP) or "latest" in rest:
            return None
        stable = not re.search(r"preview|exp|\d{2}-\d{2}", rest)
        return (stable, version, {"pro": 2, "flash": 1, "flash-lite": 0}[tier], -len(rest))
    keyed = [(key(n), n.removeprefix("models/")) for n in names]
    return [n for k, n in sorted((x for x in keyed if x[0] is not None), key=lambda x: x[0], reverse=True)]


class GeminiLLM:
    provider = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None, post: Post | None = None,
                 get: Callable[[str, dict], dict] | None = None, max_retries: int = 6,
                 sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError("no Gemini key: set GEMINI_API_KEY in your shell")
        self._post = post or (lambda url, h, b: _http(url, h, b))
        self._get = get or (lambda url, h: _http(url, h, None))
        self.max_retries, self.sleep = max_retries, sleep
        self.model = model or os.environ.get("TRACELENS_GEMINI_MODEL") or self._pick_model()
        self.schema_mode = "json_schema"  # downgraded once if the API rejects the schema

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def available_models(self) -> list[str]:
        names, token = [], ""
        for _ in range(20):
            data = self._get(f"{GEMINI_API}/models?pageSize=1000" + (f"&pageToken={token}" if token else ""),
                             self._headers())
            names += [m["name"] for m in data.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", [])]
            token = data.get("nextPageToken", "")
            if not token:
                break
        return names

    def _pick_model(self) -> str:
        ranked = rank_gemini_models(self.available_models())
        if not ranked:
            raise LLMError("no Gemini text model with generateContent is available to this key")
        return ranked[0]

    def json_call(self, system: str, messages: list[dict[str, str]], schema: dict) -> Reply:
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages]
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 32768, "responseMimeType": "application/json"},
        }
        if self.schema_mode == "json_schema":
            body["generationConfig"]["responseJsonSchema"] = schema
        else:  # JSON mode without server-side schema: state the schema in the prompt instead
            body["systemInstruction"]["parts"].append(
                {"text": "Reply with one JSON object matching this JSON Schema:\n" + json.dumps(schema)})
        data = self._send(f"{GEMINI_API}/models/{self.model}:generateContent", body, schema)
        return self._reply(data)

    def _send(self, url: str, body: dict, schema: dict) -> dict:
        delay = 5.0
        for attempt in range(self.max_retries + 1):
            try:
                return self._post(url, self._headers(), body)
            except LLMError as e:
                status = getattr(e, "status", 0)
                if status == 400 and self.schema_mode == "json_schema" and "schema" in str(e).lower():
                    self.schema_mode = "prompt"  # older/limited model: fall back to JSON mode
                    gc = body["generationConfig"]
                    gc.pop("responseJsonSchema", None)
                    body["systemInstruction"]["parts"].append(
                        {"text": "Reply with one JSON object matching this JSON Schema:\n" + json.dumps(schema)})
                    continue
                if status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    self.sleep(min(120.0, getattr(e, "retry_after", None) or delay))  # free-tier rate limits
                    delay *= 2
                    continue
                raise
        raise LLMError("Gemini API: retries exhausted")

    def _reply(self, data: dict) -> Reply:
        model = data.get("modelVersion") or self.model
        if data.get("promptFeedback", {}).get("blockReason"):
            return Reply("", "refusal", model)
        cands = data.get("candidates") or []
        if not cands:
            return Reply("", "refusal", model)
        c = cands[0]
        text = "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []) if not p.get("thought"))
        finish = c.get("finishReason", "STOP")
        if finish == "MAX_TOKENS":
            return Reply(text, "max_tokens", model)
        if finish not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            return Reply(text, "refusal", model)  # SAFETY, RECITATION, PROHIBITED_CONTENT, ...
        return Reply(_strip_fence(text), "ok", model)


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t


# ----------------------------------------------------------------------------- selection
def pick_provider(provider: str | None = None) -> str:
    p = (provider or os.environ.get("TRACELENS_LLM") or "auto").lower()
    if p in ("claude", "gemini"):
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "claude"  # the SDK reports the missing key clearly


def make_llm(provider: str | None = None, model: str | None = None, effort: str = "medium"):
    p = pick_provider(provider)
    if p == "gemini":
        return GeminiLLM(model=model if model and model.startswith("gemini") else None)
    return ClaudeLLM(model=model if model and model.startswith("claude") else None, effort=effort)
