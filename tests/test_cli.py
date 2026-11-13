import json

from tracelens.cli import main


def test_synth_then_analyze(tmp_path, capsys):
    out = tmp_path / "fx"
    assert main(["synth", "--out", str(out)]) == 0
    cfg = str(out / "tracelens.toml")

    assert main(["analyze", str(out / "z0_clean.txt"), "-c", cfg, "-q"]) == 0

    html, js = tmp_path / "r.html", tmp_path / "r.json"
    rc = main(["analyze", str(out / "z1_prio_inversion.txt"), "-c", cfg,
               "--html", str(html), "--json", str(js)])
    assert rc == 1
    assert "Priority inversion" in capsys.readouterr().out
    assert "<svg" in html.read_text(encoding="utf-8")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["summary"]["critical"] == 2
    assert data["findings"][0]["evidence_events"]


def test_fail_on_threshold(tmp_path):
    out = tmp_path / "fx"
    main(["synth", "--out", str(out)])
    # contention is 'high' -> passes when only critical fails the build
    assert main(["analyze", str(out / "z4_mutex_contention.txt"), "--fail-on", "critical", "-q"]) == 0


def test_missing_file_is_usage_error():
    assert main(["analyze", "does-not-exist.txt", "-q"]) == 2
