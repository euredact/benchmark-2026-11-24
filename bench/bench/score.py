"""Run the set's own scripts/score.py on a pred.jsonl and parse its output. Scoring is never reimplemented here."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from bench.data import DataSet, sha256_file
from bench.leaks import leak_report


BUILTIN_TOOLS = {"coarse", "any"}  # score.py's own: coarse bucket names as types; any span is a redaction


class ScoreError(Exception):
    pass


def check_tool(ds: DataSet, tool: str) -> None:
    """Refuse to score a system whose type mapping is not in labels.json (it must be committed first)."""
    if tool in BUILTIN_TOOLS:
        return
    mappings = ds.labels().get("tool_mappings", {})
    if tool not in mappings:
        raise ScoreError(
            f"labels.json of {ds.name} has no tool_mappings[{tool!r}]; commit the mapping before the first scored run"
        )


def unmapped_types(ds: DataSet, pred_path: Path, tool: str) -> Counter:
    """Native types in pred.jsonl that the tool's mapping lacks. score.py ignores them (neither hit nor false alarm),
    which would quietly hide part of what a tool redacts, so scoring refuses until they are mapped."""
    if tool == "any":
        return Counter()
    labels = ds.labels()
    known = {v["coarse"] for v in labels["fine"].values()} if tool == "coarse" else set(labels["tool_mappings"][tool])
    found: Counter = Counter()
    with open(pred_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                found.update(e["type"] for e in json.loads(line)["entities"])
    return Counter({t: n for t, n in found.items() if t not in known and not str(t).startswith("_")})


def run_scorer(ds: DataSet, pred_path: Path, tool: str) -> dict:
    if sha256_file(ds.labels_path) != ds.labels_sha256:
        raise ScoreError(f"{ds.labels_path.name} changed after the set was loaded (during the run?); its hash in "
                         f"meta.json would not match what score.py reads. Rescore with `bench score --run <dir>`.")
    check_tool(ds, tool)
    missing = unmapped_types(ds, pred_path, tool)
    if missing:
        listing = ", ".join(f"{t} ({n})" for t, n in missing.most_common())
        raise ScoreError(f"tool_mappings[{tool!r}] in {ds.labels_path.name} lacks native types the run returned: "
                         f"{listing}. Map them (and commit) before scoring; the run folder is kept, rescore with "
                         f"`bench score --run <dir>`.")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "score_out.json"
        # score.py runs from its own folder, so every path it gets must be absolute
        paths = {"gold": ds.gold_path, "pred": pred_path, "labels": ds.labels_path, "out": out}
        values = {k: Path(v).resolve() for k, v in paths.items()} | {"tool": tool}
        args = [a.format(**values) for a in ds.scorer_args]
        proc = subprocess.run(
            [sys.executable, str(ds.scorer_script), *args],
            cwd=ds.scorer_script.parent,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ScoreError(f"score.py exited {proc.returncode}:\n{proc.stderr[-2000:]}")
        payload = out.read_text(encoding="utf-8") if ds.scorer_output == "file" else proc.stdout
    try:
        result = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ScoreError(f"score.py output is not JSON ({e}); check scorer.args/output in sets.yaml") from e
    return {
        "set": ds.name,
        "tool": tool,
        "gold_sha256": ds.gold_sha256,
        "labels_sha256": ds.labels_sha256,
        "result": result,
        "summary_md": proc.stdout if ds.scorer_output == "file" else None,
        "leaks": leak_report(ds.gold_path, pred_path, ds.labels(), tool),  # harness-computed, see bench/leaks.py
    }


def write_score(path: Path, score: dict) -> None:
    path.write_text(json.dumps(score, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
