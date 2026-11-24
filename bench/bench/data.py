"""Load a benchmark set, verify every document against gold.jsonl, and iterate its documents.

A set is read-only input in the IT-250 release layout:
    docs/<lang>/<id>.txt   the input, UTF-8, LF
    gold.jsonl             id, lang, genre, band, hard, negative, sha256, text, entities[]
    labels.json            label set + tool_mappings
    scripts/score.py       the scorer
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def get_config_dir() -> Path:
    """The config folder: BENCH_CONFIG_DIR if set (tests, alternative configs), else bench/config."""
    return Path(os.environ.get("BENCH_CONFIG_DIR") or DEFAULT_CONFIG_DIR)


class IntegrityError(Exception):
    """The set on disk does not match its gold.jsonl; the run must not start."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expand(value: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise KeyError(f"environment variable {name} is not set (needed by sets.yaml)")
        return os.environ[name]

    return re.sub(r"\$\{(\w+)\}", sub, value)


@dataclass(frozen=True)
class Doc:
    id: str
    lang: str
    text: str
    record: dict  # the full gold.jsonl line (genre, band, hard, negative, entities, ...)

    @property
    def entities(self) -> list[dict]:
        return self.record.get("entities", [])


@dataclass
class DataSet:
    name: str
    root: Path
    gold_path: Path
    labels_path: Path
    scorer_script: Path
    scorer_args: list[str]
    scorer_output: str
    docs: list[Doc] = field(default_factory=list)
    recording_docs: list[str] = field(default_factory=list)  # adapter tests: one en, one nl, one pl document
    gold_sha256: str = ""
    labels_sha256: str = ""

    def __iter__(self):
        return iter(self.docs)

    def __len__(self):
        return len(self.docs)

    def by_id(self) -> dict[str, Doc]:
        return {d.id: d for d in self.docs}

    def labels(self) -> dict:
        return json.loads(self.labels_path.read_text(encoding="utf-8"))


def set_config(name: str, config_dir: Path | None = None) -> dict:
    config_dir = config_dir or get_config_dir()
    sets = yaml.safe_load((config_dir / "sets.yaml").read_text(encoding="utf-8"))["sets"]
    if name not in sets:
        raise KeyError(f"unknown set {name!r}; known: {', '.join(sorted(sets))}")
    return sets[name]


def load_set(name: str, config_dir: Path | None = None, root: Path | None = None) -> DataSet:
    """Load set `name` from sets.yaml and verify it. `root` overrides the configured path (tests)."""
    config_dir = config_dir or get_config_dir()
    cfg = set_config(name, config_dir)
    root = Path(root) if root is not None else Path(_expand(cfg["root"]))
    release_labels = root / cfg["labels"]
    ds = DataSet(
        name=name,
        root=root,
        gold_path=root / cfg["gold"],
        labels_path=config_dir / cfg["labels_file"] if cfg.get("labels_file") else release_labels,
        scorer_script=root / cfg["scorer"]["script"],
        scorer_args=list(cfg["scorer"]["args"]),
        scorer_output=cfg["scorer"]["output"],
        recording_docs=list(cfg.get("recording_docs", [])),
    )
    ds.docs = _load_and_verify(ds, root / cfg["docs_dir"])
    if ds.labels_path != release_labels:
        _check_labels_match_release(ds.labels_path, release_labels)
    ds.gold_sha256 = sha256_file(ds.gold_path)
    ds.labels_sha256 = sha256_file(ds.labels_path)
    return ds


def _load_and_verify(ds: DataSet, docs_dir: Path) -> list[Doc]:
    for p in (ds.gold_path, ds.labels_path, ds.scorer_script):
        if not p.is_file():
            raise IntegrityError(f"{ds.name}: missing {p}")

    problems: list[str] = []
    docs: list[Doc] = []
    seen: set[str] = set()
    with open(ds.gold_path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            doc_id, lang = rec["id"], rec["lang"]
            if doc_id in seen:
                problems.append(f"{doc_id}: duplicate id in gold.jsonl (line {n})")
                continue
            seen.add(doc_id)
            path = docs_dir / lang / f"{doc_id}.txt"
            if not path.is_file():
                problems.append(f"{doc_id}: missing {path}")
                continue
            data = path.read_bytes()
            if sha256_bytes(data) != rec["sha256"]:
                problems.append(f"{doc_id}: sha256 of {path.name} does not match gold.jsonl")
                continue
            text = data.decode("utf-8")
            if "text" in rec and rec["text"] != text:
                problems.append(f"{doc_id}: file text differs from gold.jsonl text")
                continue
            problems.extend(_check_entities(doc_id, text, rec.get("entities", [])))
            docs.append(Doc(id=doc_id, lang=lang, text=text, record=rec))

    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise IntegrityError(f"{ds.name}: {len(problems)} problem(s), refusing to run:\n  {shown}{more}")
    if not docs:
        raise IntegrityError(f"{ds.name}: gold.jsonl has no documents")
    return docs


def _check_labels_match_release(ours: Path, release: Path) -> None:
    """The repo's labels file may only add tool_mappings; the label set itself must be the release's."""
    a = json.loads(ours.read_text(encoding="utf-8"))
    b = json.loads(release.read_text(encoding="utf-8"))
    diff = sorted(k for k in set(a) | set(b) if k != "tool_mappings" and a.get(k) != b.get(k))
    if diff:
        raise IntegrityError(f"{ours} differs from the release labels.json outside tool_mappings: {', '.join(diff)}")
    changed = [t for t, m in b.get("tool_mappings", {}).items()
               if isinstance(m, dict) and any(a["tool_mappings"].get(t, {}).get(k) != v for k, v in m.items()
                                              if not k.startswith("_"))]
    if changed:
        raise IntegrityError(f"{ours} changes release mappings (only additions allowed): {', '.join(changed)}")


def _check_entities(doc_id: str, text: str, entities: list[dict]) -> list[str]:
    """Gold sanity: offsets inside the text, non-empty, and matching the entity's own text when given."""
    out = []
    for i, e in enumerate(entities):
        s, t = e.get("start"), e.get("end")
        if not (isinstance(s, int) and isinstance(t, int) and 0 <= s < t <= len(text)):
            out.append(f"{doc_id}: entity {i} has bad offsets ({s}, {t})")
        elif "text" in e and text[s:t] != e["text"]:
            out.append(f"{doc_id}: entity {i} text {e['text']!r} != document[{s}:{t}] {text[s:t]!r}")
    return out
