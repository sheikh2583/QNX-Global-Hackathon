"""Run every detector over a trace and return ranked, numbered findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .detectors import ALL
from .findings import Finding
from .ingest.traceprinter import parse_file, parse_text
from .model.trace import TraceModel


SYMPTOMS = {"deadline_miss"}


@dataclass
class Analysis:
    model: TraceModel
    findings: list[Finding]
    config: Config
    errors: list[str] = field(default_factory=list)


def analyze_model(model: TraceModel, cfg: Config | None = None) -> Analysis:
    cfg = cfg or Config()
    findings: list[Finding] = []
    errors: list[str] = []
    for name, detect in ALL:
        try:
            findings.extend(detect(model, cfg))
        except Exception as exc:  # one broken detector must not hide the others
            errors.append(f"{name}: {exc!r}")
    # Root causes before symptoms: a deadline miss sorts after the inversion that caused it.
    findings.sort(key=lambda f: (-f.rank, f.kind in SYMPTOMS, f.t_start))
    for i, f in enumerate(findings, start=1):
        f.id = f"TL-{i:03d}"
    return Analysis(model=model, findings=findings, config=cfg, errors=errors)


def analyze_file(path: str | Path, cfg: Config | None = None, cycles_per_sec: int | None = None) -> Analysis:
    return analyze_model(TraceModel(parse_file(path, cycles_per_sec)), cfg)


def analyze_text(text: str, cfg: Config | None = None, cycles_per_sec: int | None = None) -> Analysis:
    return analyze_model(TraceModel(parse_text(text, cycles_per_sec=cycles_per_sec)), cfg)
