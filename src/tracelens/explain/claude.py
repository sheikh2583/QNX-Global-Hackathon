"""Model-backed explanations (Claude or Gemini), validated against the evidence they cite.

Flow per finding:
  evidence pack -> prompt -> Claude (JSON schema output) -> citation validator
  -> on failure, one corrective retry with the validator's complaints
  -> result marked verified / unverified, cached on disk by prompt hash.

The provider comes from ``tracelens.llm`` (Claude via the optional ``anthropic`` extra, or Gemini
over plain HTTPS); nothing here is imported by the analysis core.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..analyze import Analysis
from ..findings import Finding
from ..llm import ClaudeLLM, make_llm
from .citations import validate
from .evidence import build_pack, format_pack
from .prompts import SCHEMA, SYSTEM, retry_prompt, user_prompt

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
PROMPT_VERSION = "explain-v2-typed-claims"


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
    def __init__(self, client: Any | None = None, model: str | None = None,
                 effort: str = DEFAULT_EFFORT, cache_dir: str | Path | None = ".tracelens-cache/explain",
                 max_attempts: int = 2, llm: Any | None = None, provider: str | None = None):
        if llm is None:
            llm = (ClaudeLLM(model=model, effort=effort, client=client) if client is not None
                   else make_llm(provider, model, effort))
        self.llm = llm
        self.model = llm.model
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
                resp = self.llm.json_call(SYSTEM, messages, SCHEMA)
                if resp.stop == "refusal":
                    result.error = "model declined to answer"
                    break
                if resp.stop == "max_tokens":
                    result.error = "response truncated (max_tokens)"
                    break
                text = resp.text
                result.model = resp.model
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    result.error = f"invalid JSON from model: {exc}"
                    break
                result.data = data
                result.problems = validate(data, pack.allowed_ids, pack.core_ids, a.model)
                result.verified = not result.problems
                if result.verified:
                    break
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": retry_prompt(result.problems)}]
        except Exception as exc:  # API/network errors become a visible, non-fatal result
            result.error = f"{type(exc).__name__}: {exc}"
            return result
        self._cache_put(key, result)
        return result

    # --------------------------------------------------------------- private
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
        if self.cache_dir is None or not result.verified:
            return  # only verified explanations are reused; failures are retried on the next run
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
