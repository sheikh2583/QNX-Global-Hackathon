"""Fix-and-verify loop, end to end with a scripted model, builder and target (no QNX, no API)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracelens.config import Config, Deadline
from tracelens.fix import BuildResult, FixAgent, HostCheckBuilder, ScopeError, Workspace
from tracelens.testing import scenarios as S

ROOT = Path(__file__).resolve().parents[1]
ZOO = ROOT / "bugzoo"
REFERENCE = (ZOO / "reference" / "z1_infusion_pump.c").read_text(encoding="utf-8")


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        return SimpleNamespace(stop_reason="end_turn", model=kw["model"],
                               content=[SimpleNamespace(type="text", text=json.dumps(r))])


def patch(content, path="main.c", why="semaphore has no owner; use a PI mutex"):
    return {"diagnosis": why, "changes": [{"path": path, "content": content}], "expected_effect": "no inversion"}


class FakeBuilder:
    def build(self, sources, include_dirs, out):
        text = "".join(Path(s).read_text(encoding="utf-8") for s in sources)
        if "SYNTAX_ERROR" in text:
            return BuildResult(False, None, "main.c:12:1: error: expected ';' before '}' token")
        Path(out).write_bytes(b"\x7fELF")
        return BuildResult(True, Path(out), "")


def fake_capturer(binary, ws_root, label, i, out):
    """Plays the QNX target: the trace reflects what the patched source actually does."""
    src = (Path(ws_root) / "main.c").read_text(encoding="utf-8")
    text = S.z1_prio_inversion() if "sem_wait" in src else S.z0_clean()
    p = Path(out) / "traces" / f"{label}-{i}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def zoo(tmp_path):
    shutil.copytree(ZOO / "z1_infusion_pump", tmp_path / "z1_infusion_pump")
    shutil.copytree(ZOO / "common", tmp_path / "common")
    return tmp_path


@pytest.fixture
def cfg():
    c = Config()
    c.deadlines["control"] = Deadline(budget_us=1000, period_us=10_000)
    return c


def agent(zoo, cfg, model, **kw):
    return FixAgent(zoo / "z1_infusion_pump", [zoo / "common"], cfg, FakeBuilder(), fake_capturer,
                    zoo / "bundle", client=model, **kw)


def test_reference_fix_is_verified_and_bundled(zoo, cfg):
    model = FakeModel([patch(REFERENCE)])
    res = agent(zoo, cfg, model).run()
    assert res.status == "VERIFIED" and len(res.attempts) == 1 and not res.quick
    assert "priority_inversion" in res.targets
    call = model.calls[0]
    prompt = call["messages"][0]["content"]
    assert "<findings>" in prompt and "<evidence" in prompt and 'editable="no"' in prompt
    assert call["output_config"]["effort"] == "high" and call["fallbacks"] == "default"
    b = zoo / "bundle"
    for f in ("SUMMARY.md", "result.json", "transcript.json", "attempt-1/patch.diff", "attempt-1/verdict.json"):
        assert (b / f).exists(), f
    diff = (b / "attempt-1/patch.diff").read_text()
    assert "-    sem_destroy(&buf_lock);" in diff and "+    pthread_mutex_destroy(&buf_lock);" in diff
    assert "VERIFIED" in (b / "SUMMARY.md").read_text()


def test_compile_error_is_fed_back(zoo, cfg):
    model = FakeModel([patch(REFERENCE.replace("int main", "SYNTAX_ERROR int main")), patch(REFERENCE)])
    res = agent(zoo, cfg, model).run()
    assert res.status == "VERIFIED"
    assert [a.stage for a in res.attempts] == ["build", "verdict"]
    assert "expected ';'" in model.calls[1]["messages"][-1]["content"]


def test_guardrails_reject_edits_outside_the_workload(zoo, cfg):
    model = FakeModel([patch("hacked", path="../common/tl.h"), patch(REFERENCE)])
    res = agent(zoo, cfg, model).run()
    assert res.attempts[0].stage == "scope" and res.status == "VERIFIED"
    assert (zoo / "common" / "tl.h").read_text() != "hacked"


def test_cosmetic_patch_is_not_fixed(zoo, cfg):
    src = (zoo / "z1_infusion_pump" / "main.c").read_text()
    model = FakeModel([patch(src + "\n/* tidy */\n"), patch(src + "\n/* tidy again */\n")])
    res = agent(zoo, cfg, model, max_attempts=2).run()
    assert res.status == "NOT FIXED" and len(res.attempts) == 2
    assert "still present" in model.calls[1]["messages"][-1]["content"]


def test_source_only_ablation_hides_the_trace(zoo, cfg):
    model = FakeModel([patch(REFERENCE)])
    agent(zoo, cfg, model, context="source-only").run()
    prompt = model.calls[0]["messages"][0]["content"]
    assert "<findings>" not in prompt and "<evidence" not in prompt and "source alone" in prompt


def test_nothing_to_fix_makes_no_model_call(zoo, cfg):
    (zoo / "z1_infusion_pump" / "main.c").write_text(REFERENCE)  # already fixed
    model = FakeModel([])
    res = agent(zoo, cfg, model).run()
    assert res.status == "NOTHING TO FIX" and model.calls == []


def test_workspace_scope_rules(tmp_path):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "main.c").write_text("int main(void){return 0;}\n")
    ws = Workspace.create(tmp_path / "w", tmp_path / "sandbox", [])
    for bad in ("/etc/passwd", "../x.c", "new.c", "main.py"):
        with pytest.raises(ScopeError):
            ws.apply([{"path": bad, "content": "x"}])
    assert ws.apply([{"path": "main.c", "content": "int main(void){return 1;}\n"}]) == ["main.c"]
    assert (tmp_path / "w" / "main.c").read_text().endswith("return 0;}\n")  # original untouched


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("gcc"), reason="needs Linux gcc")
def test_hostcheck_builder_compiles_reference_and_rejects_garbage(zoo, tmp_path):
    b = HostCheckBuilder(stubs=ZOO / "hostcheck")
    good = tmp_path / "good.c"
    good.write_text(REFERENCE)
    assert b.build([good], [zoo / "common"], tmp_path / "bin").ok
    bad = tmp_path / "bad.c"
    bad.write_text("int main(void) { return }\n")
    r = b.build([bad], [zoo / "common"], tmp_path / "bin2")
    assert not r.ok and "error" in r.log
