"""Guardrails for agent patches: what the fix agent may touch.

The agent edits a *copy* of one workload directory. It may only change files
that already exist there with an allowed extension; it can never touch the
shared header, the reference fixes, tests, detectors, or anything outside the
workload, so it cannot "fix" a bug by blinding the checker.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ALLOWED_SUFFIXES = {".c", ".h"}
MAX_FILE_BYTES = 200_000


class ScopeError(ValueError):
    """A proposed change falls outside the allowed patch scope."""


@dataclass
class Workspace:
    """A sandbox copy of ``bugzoo/<workload>/`` plus read-only includes."""

    root: Path  # sandbox copy of the workload directory
    include_dirs: list[Path]  # read-only, e.g. bugzoo/common

    @classmethod
    def create(cls, workload_dir: str | Path, sandbox: str | Path, include_dirs: list[str | Path]) -> Workspace:
        src = Path(workload_dir)
        dst = Path(sandbox)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return cls(root=dst, include_dirs=[Path(p) for p in include_dirs])

    def files(self) -> dict[str, str]:
        out = {}
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and p.suffix in ALLOWED_SUFFIXES:
                out[p.relative_to(self.root).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        return out

    def check(self, path: str, content: str) -> Path:
        """Validate one proposed change; return the absolute path it would write."""
        rel = PurePosixPath(path.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ScopeError(f"{path}: must be a relative path inside the workload")
        if rel.suffix not in ALLOWED_SUFFIXES:
            raise ScopeError(f"{path}: only {sorted(ALLOWED_SUFFIXES)} files may be changed")
        target = self.root / Path(*rel.parts)
        if not target.exists():
            raise ScopeError(f"{path}: not an existing file of this workload (no new files)")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ScopeError(f"{path}: replacement is too large")
        return target

    def apply(self, changes: list[dict]) -> list[str]:
        """Validate every change first, then write them all (all or nothing)."""
        if not changes:
            raise ScopeError("the patch changes no files")
        targets = [(self.check(c["path"], c["content"]), c["content"]) for c in changes]
        for target, content in targets:
            target.write_text(content, encoding="utf-8", newline="\n")
        return [c["path"] for c in changes]
