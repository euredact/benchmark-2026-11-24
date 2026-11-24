"""End to end through the CLI: BENCH_DATA_DIR/it360 points at the mini set, BENCH_CONFIG_DIR at the test config."""

import json

from bench.cli import main


def test_run_then_score_from_raw(mini_root, config_dir, tmp_path, monkeypatch, capsys):
    (tmp_path / "data" / "it360").symlink_to(mini_root)
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BENCH_CONFIG_DIR", str(config_dir))
    runs = tmp_path / "runs"

    assert main(["run", "--system", "gold", "--set", "it360", "--runs-dir", str(runs)]) == 0
    (rd,) = runs.iterdir()
    assert json.loads((rd / "score.json").read_text())["result"]["results"]["ALL|binary|overlap"]["f1"] == 1.0

    assert main(["score", "--run", str(rd), "--from-raw"]) == 0
    assert "identical to score.json" in capsys.readouterr().out


def test_tampered_set_is_refused(mini_root, config_dir, tmp_path, monkeypatch, capsys):
    (tmp_path / "data" / "it360").symlink_to(mini_root)
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BENCH_CONFIG_DIR", str(config_dir))
    p = mini_root / "docs" / "nl" / "mini-nl-001.txt"
    p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert main(["run", "--system", "gold", "--set", "it360", "--runs-dir", str(tmp_path / "runs")]) == 2
    assert "refusing to run" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


def test_relative_run_path(mini_root, config_dir, tmp_path, monkeypatch, capsys):
    """score.py runs from its own folder, so every path handed to it must be absolute."""
    (tmp_path / "data" / "it360").symlink_to(mini_root)
    monkeypatch.setenv("BENCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BENCH_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--system", "gold", "--set", "it360", "--runs-dir", "runs"]) == 0
    (rd,) = (tmp_path / "runs").iterdir()
    assert main(["score", "--run", f"runs/{rd.name}", "--from-raw"]) == 0
    assert main(["score", "--run", f"runs/{rd.name}"]) == 0
