"""Claude-backed explanations, validated against the evidence they cite.

Flow per finding:
  evidence pack -> prompt -> Claude (JSON schema output) -> citation validator
  -> on failure, one corrective retry with the validator's complaints
  -> result marked verified / unverified, cached on disk by prompt hash.

The ``anthropic`` package is an optional extra (``pip install tracelens[ai]``);
nothing here is imported by the analysis core.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..analyze import Analysis
from ..findings import Finding
from .citations import validate
from .evidence import build_pack, format_pack
from .prompts import SCHEMA, SYSTEM, retry_prompt, user_prompt

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
PROMPT_VERSION = "explain-v1"


@dataclass
class Explanation:
    finding_id: str
    data: dict[str, Any] | None = None
    verified: bool = False
    problems: list[str] = field(default_factory=list)
    model: str = ""
    attempts: int = 0
    cached: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Explainer:
    def __init__(self, client: Any | None = None, model: str = DEFAULT_MODEL,
                 effort: str = DEFAULT_EFFORT, cache_dir: str | Path | None = ".tracelens-cache/explain",
                 max_attempts: int = 2):
        if client is None:
            import anthropic  # optional dependency
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_attempts = max_attempts

    # ---------------------------------------------------------------- public
    def explain_analysis(self, a: Analysis, sources: dict[str, str] | None = None,
                         limit: int | None = None) -> dict[str, Explanation]:
        out: dict[str, Explanation] = {}
        for f in a.findings[:limit]:
            out[f.id] = self.explain(a, f, sources)
        return out

    def explain(self, a: Analysis, finding: Finding, sources: dict[str, str] | None = None) -> Explanation:
        pack = build_pack(a.model, finding)
        prompt = user_prompt(finding, format_pack(a.model, pack), sources)
        key = self._key(prompt)
        hit = self._cache_get(key)
        if hit is not None:
            hit.finding_id, hit.cached = finding.id, True
            return hit

        result = Explanation(finding_id=finding.id, model=self.model)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        try:
            for attempt in range(1, self.max_attempts + 1):
                result.attempts = attempt
                resp = self._call(messages)
                if resp.stop_reason == "refusal":
                    result.error = "model declined to answer"
                    break
                if resp.stop_reason == "max_tokens":
                    result.error = "response truncated (max_tokens)"
                    break
                text = next((b.text for b in resp.content if b.type == "text"), "")
                result.model = getattr(resp, "model", self.model)
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    result.error = f"invalid JSON from model: {exc}"
                    break
                result.data = data
                result.problems = validate(data, pack.allowed_ids, pack.core_ids)
                result.verified = not result.problems
                if result.verified:
                    break
                messages += [{"role": "assistant", "content": resp.content},
                             {"role": "user", "content": retry_prompt(result.problems)}]
        except Exception as exc:  # API/network errors become a visible, non-fatal result
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        self._cache_put(key, result)
        return result

    # --------------------------------------------------------------- private
    def _call(self, messages: list[dict[str, Any]]):
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",  # re-run on a fallback model if the request is declined
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=messages,
        )

    def _key(self, prompt: str) -> str:
        h = hashlib.sha256()
        for part in (PROMPT_VERSION, self.model, self.effort, SYSTEM, json.dumps(SCHEMA, sort_keys=True), prompt):
            h.update(part.encode("utf-8"))
            h.update(b"\0")
        return h.hexdigest()

    def _cache_get(self, key: str) -> Explanation | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return Explanation(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, TypeError, ValueError):
            return None

    def _cache_put(self, key: str, result: Explanation) -> None:
        if self.cache_dir is None or result.data is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
