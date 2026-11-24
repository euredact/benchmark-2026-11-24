"""Run one system configuration on one set and write a run folder:

    runs/<UTC timestamp>_<system>_<config>_<set>/
        pred.jsonl         scorer input, one line per document (failed and unsupported ones included, empty)
        raw/<doc id>.json  the untouched response of every call, enough to re-score without the system
        meta.json          conditions: versions, hashes, latency, billed units, failures, unsupported, unresolved
        score.json         the parsed output of the set's score.py
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from bench.adapters import Adapter, get_adapter_class
from bench.data import PROMPTS_DIR, DataSet, Doc, get_config_dir, sha256_file
from bench.score import check_tool, run_scorer, write_score

BENCH_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("BENCH_RUNS_DIR", BENCH_DIR.parent / "runs"))


def system_config(system: str, config_name: str, config_dir: Path | None = None) -> dict:
    config_dir = config_dir or get_config_dir()
    systems = yaml.safe_load((config_dir / "systems.yaml").read_text(encoding="utf-8"))["systems"]
    if system not in systems:
        raise KeyError(f"unknown system {system!r}; known: {', '.join(sorted(systems))}")
    configs = systems[system]["configs"]
    if config_name not in configs:
        raise KeyError(f"system {system!r} has no config {config_name!r}; known: {', '.join(sorted(configs))}")
    return configs[config_name]


def _hash_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _git_commit() -> str | None:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BENCH_DIR, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=BENCH_DIR, capture_output=True, text=True)
        return rev.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def build_adapter(cfg: dict, ds: DataSet) -> Adapter:
    cls = get_adapter_class(cfg["adapter"])
    # Only the gold replay may see gold; real adapters get the text and the language, nothing else.
    context = {"dataset": ds} if cls.name == "gold" else {}
    return cls(cfg, context)


EXCLUDE_MODES = ("all", "unmatched")


def pred_line(adapter: Adapter, doc: Doc, raw_record: dict) -> tuple[dict, int]:
    """pred.jsonl line for one document from its raw record. Used by the run and by --from-raw alike."""
    if raw_record["status"] != "ok":
        return {"id": doc.id, "entities": []}, 0
    parsed = adapter.parse(raw_record["response"], doc.text, doc.lang)
    excluded = set(adapter.config.get("exclude_types", []))  # types the configuration switches off, as a user would
    mode = adapter.config.get("exclude_mode", "all")
    if mode not in EXCLUDE_MODES:
        raise ValueError(f"exclude_mode {mode!r} is not one of {', '.join(EXCLUDE_MODES)}")
    # `unmatched`: a switched-off type only loses the spans that overlap no redactable gold span, so switching a type
    # off removes its over-redaction but never turns one of its hits into a leak. Gold is read here, after the system
    # has answered; the adapter never sees it.
    gold = [(e["start"], e["end"]) for e in doc.record["entities"] if e["redact"]] if mode == "unmatched" else []

    def keep(s) -> bool:
        return s.type not in excluded or any(s.start < ge and gs < s.end for gs, ge in gold)

    ents = [s.to_pred() for s in sorted(parsed.spans, key=lambda s: (s.start, s.end, s.type)) if keep(s)]
    return {"id": doc.id, "entities": ents}, parsed.unresolved


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class RateLimiter:
    """Spaces the starts of calls at least 60 / max_per_min seconds apart, across threads (retries included)."""

    def __init__(self, max_per_min: float | None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval = 60.0 / max_per_min if max_per_min else 0.0
        self._next, self._lock, self._clock, self._sleep = 0.0, threading.Lock(), clock, sleep

    def __call__(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            self._sleep(start - now)


def _call_with_retries(adapter: Adapter, doc: Doc, retries: int, backoff_s: float, sleep: Callable[[float], None],
                       before_call: Callable[[], None] = lambda: None):
    errors = []
    for attempt in range(retries + 1):
        before_call()
        try:
            return adapter.detect(doc.text, doc.lang), attempt + 1, errors
        except Exception as e:  # noqa: BLE001 - any failure is retried, then recorded
            errors.append(f"{type(e).__name__}: {e}"[:500])
            if attempt < retries:
                sleep(backoff_s * 2**attempt)
    return None, retries + 1, errors


def process_doc(adapter: Adapter, cfg: dict, doc: Doc, sleep: Callable[[float], None] = time.sleep,
                before_call: Callable[[], None] = lambda: None) -> dict:
    """Call the system on one document (unless its language is unsupported) and return the raw record."""
    if cfg.get("languages") and doc.lang not in cfg["languages"]:
        return {"doc_id": doc.id, "lang": doc.lang, "status": "unsupported"}
    result, attempts, errors = _call_with_retries(adapter, doc, cfg.get("retries", 3), cfg.get("backoff_s", 2.0), sleep,
                                                  before_call)
    if result is None:
        return {"doc_id": doc.id, "lang": doc.lang, "status": "failed", "attempts": attempts, "errors": errors}
    return {"doc_id": doc.id, "lang": doc.lang, "status": "ok", "attempts": attempts, "errors": errors,
            "model_version": result.model_version, "billed_units": result.billed_units,
            "latency_s": result.latency_s, "response": result.raw}


def config_files(cfg: dict, config_dir: Path) -> dict[str, str]:
    """sha256 of every file a system config points to (`*_file` keys: prompts/ for prompt_file, else config/)."""
    out = {}
    for key, rel in sorted(cfg.items()):
        if key.endswith("_file") and rel:
            base = PROMPTS_DIR if key == "prompt_file" else config_dir
            out[rel] = sha256_file(base / rel)
    return out


def run(system: str, ds: DataSet, config_name: str = "default", runs_dir: Path = RUNS_DIR,
        config_dir: Path | None = None, sleep: Callable[[float], None] = time.sleep, score: bool = True,
        workers: int = 1, max_per_min: float | None = None, reuse: list[tuple[Path, DataSet]] | None = None) -> Path:
    """Run a system on a set. `workers` documents are in flight at once (the adapter must be thread-safe for more than
    one); `max_per_min` caps how often a call starts, retries included. Each raw record is written as its document is
    answered; pred.jsonl and meta.json follow document order.

    `reuse`: earlier runs of the same system and configuration, each with the set it was made on. A document whose id
    and text are identical in that set, and that the earlier run answered, gets the earlier raw answer instead of a
    call (e.g. a set that extends another one). Reused answers are listed in meta.json and not counted as billed."""
    config_dir = config_dir or get_config_dir()
    cfg = system_config(system, config_name, config_dir)
    tool = cfg["tool"]
    check_tool(ds, tool)  # fail before spending money, not after
    files = config_files(cfg, config_dir)  # and before a missing prompt or config file
    adapter = build_adapter(cfg, ds)
    adapter.preflight()  # and before a missing key
    reusable = _reusable(system, cfg, ds, reuse or [])

    started = datetime.now(timezone.utc)
    run_dir = Path(runs_dir) / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{system}_{config_name}_{ds.name}"
    (run_dir / "raw").mkdir(parents=True)

    preds, per_doc = [], {}
    billed_total: Counter = Counter()
    versions: Counter = Counter()
    failed, unsupported, unresolved_total = [], [], 0
    limiter = RateLimiter(max_per_min, sleep=sleep)

    def call(doc: Doc) -> dict:  # the raw record is on disk as soon as the document is answered
        if doc.id in reusable:
            record = json.loads(reusable[doc.id].read_text(encoding="utf-8"))
            record["reused_from"] = reusable[doc.id].parent.parent.name
        else:
            record = process_doc(adapter, cfg, doc, sleep, limiter)
        (run_dir / "raw" / f"{doc.id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return record

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [(doc, pool.submit(call, doc)) for doc in ds]
    for doc, future in futures:
        record = future.result()
        if record["status"] == "unsupported":
            unsupported.append(doc.id)
            per_doc[doc.id] = {"status": "unsupported"}
        elif record["status"] == "failed":
            failed.append(doc.id)
            per_doc[doc.id] = {"status": "failed", "attempts": record["attempts"], "errors": record["errors"]}
        else:
            if "reused_from" not in record:
                billed_total.update(record["billed_units"])
            versions[record["model_version"]] += 1
            per_doc[doc.id] = {"status": "ok", "attempts": record["attempts"], "latency_s": record["latency_s"],
                               "billed_units": record["billed_units"]}
            if "reused_from" in record:
                per_doc[doc.id]["reused_from"] = record["reused_from"]
        line, unresolved = pred_line(adapter, doc, record)
        if record["status"] == "ok":
            per_doc[doc.id]["unresolved"] = unresolved
        unresolved_total += unresolved
        preds.append(line)

    write_jsonl(run_dir / "pred.jsonl", preds)
    prompt = cfg.get("prompt_file")
    meta = {
        "system": system,
        "adapter": cfg["adapter"],
        "config": config_name,
        "config_sha256": _hash_json(cfg),
        "config_values": cfg,
        "tool": tool,
        "model_versions": dict(versions),
        "adapter_versions": adapter.versions(),
        "internal_only": bool(cfg.get("internal_only", adapter.internal_only)),
        "external": bool(cfg.get("external", False)),
        "run_started_utc": started.isoformat(),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(),
        "set": ds.name,
        "n_docs": len(ds),
        "gold_sha256": ds.gold_sha256,
        "labels_sha256": ds.labels_sha256,
        "prompt": prompt,
        "prompt_sha256": files.get(prompt),
        "config_files": files,
        "harness_commit": _git_commit(),
        "hardware": {"platform": platform.platform(), "machine": platform.machine(), "cpus": os.cpu_count(),
                     "python": platform.python_version()},
        "billed_units_total": dict(billed_total),
        "failed": failed,
        "unsupported": unsupported,
        "unresolved_total": unresolved_total,
        "retries_total": sum(max(0, d.get("attempts", 1) - 1) for d in per_doc.values() if "reused_from" not in d),
        "reused": {name: sorted(i for i, d in per_doc.items() if d.get("reused_from") == name)
                   for name in sorted({d["reused_from"] for d in per_doc.values() if "reused_from" in d})},
        "concurrency": {"workers": max(1, workers), "max_per_min": max_per_min},
        "per_doc": per_doc,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if score:
        write_score(run_dir / "score.json", run_scorer(ds, run_dir / "pred.jsonl", tool))
    return run_dir


def _reusable(system: str, cfg: dict, ds: DataSet, reuse: list[tuple[Path, DataSet]]) -> dict[str, Path]:
    """doc id -> raw record of an earlier run to reuse; refuses a run of another system, configuration or gold."""
    texts = {d.id: d.text for d in ds}
    out: dict[str, Path] = {}
    for run_dir, src in reuse:
        run_dir = Path(run_dir)
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        if meta["system"] != system or meta["config_values"] != cfg:
            raise ValueError(f"{run_dir.name} is not a run of {system} with this configuration; its answers would differ")
        if meta.get("derived_from"):
            raise ValueError(f"{run_dir.name} is derived; reuse the run that called the system")
        if meta["set"] != src.name or meta["gold_sha256"] != src.gold_sha256:
            raise ValueError(f"{run_dir.name} was made on {meta['set']} with gold {meta['gold_sha256'][:12]}, not {src.name}'s current gold")
        for doc in src:
            raw = run_dir / "raw" / f"{doc.id}.json"
            if texts.get(doc.id) == doc.text and doc.id not in out and raw.is_file():
                if json.loads(raw.read_text(encoding="utf-8")).get("status") == "ok":
                    out[doc.id] = raw
    return out


def recordings_dir() -> Path:
    """Recorded responses for the adapter tests. They contain document text, so they live with the data, not in git."""
    if os.environ.get("BENCH_RECORDINGS_DIR"):
        return Path(os.environ["BENCH_RECORDINGS_DIR"])
    if os.environ.get("BENCH_DATA_DIR"):
        return Path(os.environ["BENCH_DATA_DIR"]) / "recordings"
    raise KeyError("set BENCH_RECORDINGS_DIR or BENCH_DATA_DIR")


def record(system: str, ds: DataSet, config_name: str = "default", doc_ids: list[str] | None = None,
           out_root: Path | None = None, config_dir: Path | None = None) -> list[Path]:
    """Call the system on a few documents and store each raw record with the prediction parsed from it."""
    config_dir = config_dir or get_config_dir()
    cfg = system_config(system, config_name, config_dir)
    doc_ids = doc_ids or ds.recording_docs
    if not doc_ids:
        raise ValueError(f"{ds.name} has no recording_docs in sets.yaml; pass --docs")
    by_id = ds.by_id()
    missing = [d for d in doc_ids if d not in by_id]
    if missing:
        raise KeyError(f"not in {ds.name}: {', '.join(missing)}")
    adapter = build_adapter(cfg, ds)
    adapter.preflight()
    out_dir = (out_root or recordings_dir()) / ds.name / f"{system}_{config_name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for doc_id in doc_ids:
        doc = by_id[doc_id]
        rec = process_doc(adapter, cfg, doc)
        if rec["status"] == "failed":
            raise RuntimeError(f"{system} failed on {doc_id}: {rec['errors'][-1]}")
        payload = {
            "system": system, "config": config_name, "config_values": cfg, "config_files": config_files(cfg, config_dir),
            "doc_id": doc_id, "doc_sha256": doc.record["sha256"], "adapter_versions": adapter.versions(),
            "recorded_utc": datetime.now(timezone.utc).isoformat(), "record": rec,
            "pred": pred_line(adapter, doc, rec)[0],
        }
        path = out_dir / f"{doc_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def derive(run_dir: Path, ds: DataSet, config_name: str, runs_dir: Path = RUNS_DIR,
           config_dir: Path | None = None, source: DataSet | None = None) -> Path:
    """A run of another configuration of the same system, built from an existing run's raw responses without calling
    the system again. Only configurations that change how raw output is read (exclude_types and exclude_mode, thresholds applied in
    parse) may be derived: everything that reaches the system must be identical, or the raw responses would differ.
    `ds` may be another set than the run's when its documents are identical (same ids, same texts), e.g. the same texts
    under another gold: pass the run's own set as `source`, which must still have the gold the run was made on."""
    src = Path(run_dir)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    config_dir = config_dir or get_config_dir()
    if meta["set"] != ds.name:
        own = source
        if own is None or own.name != meta["set"]:
            raise ValueError(f"{src.name} was made on {meta['set']}; pass that set as source to derive it onto {ds.name}")
        if meta["gold_sha256"] != own.gold_sha256:
            raise ValueError(f"{src.name} was made on {meta['set']} with gold {meta['gold_sha256'][:12]}, not its current gold")
        if [(d.id, d.text) for d in own] != [(d.id, d.text) for d in ds]:
            raise ValueError(f"{ds.name} does not hold the same documents as {meta['set']}; derive needs identical texts")
    elif meta["gold_sha256"] != ds.gold_sha256:
        raise ValueError(f"{src.name} was made on {meta['set']} with gold {meta['gold_sha256'][:12]}, not this {ds.name}")
    if meta.get("derived_from"):
        raise ValueError(f"{src.name} is itself derived; derive from the run that called the system")
    cfg = system_config(meta["system"], config_name, config_dir)
    parse_only = {"exclude_types", "exclude_mode", "threshold"}
    differ = sorted(k for k in set(cfg) | set(meta["config_values"])
                    if k not in parse_only and cfg.get(k) != meta["config_values"].get(k))
    if differ:
        raise ValueError(f"config {config_name!r} differs from {meta['config']!r} in what reaches the system ({', '.join(differ)}); "
                         f"run it with `bench run` instead")
    check_tool(ds, cfg["tool"])
    adapter = get_adapter_class(cfg["adapter"])(cfg, {})
    started = datetime.now(timezone.utc)
    out = Path(runs_dir) / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{meta['system']}_{config_name}_{ds.name}"
    shutil.copytree(src / "raw", out / "raw")
    preds, unresolved = [], 0
    for doc in ds:
        record = json.loads((out / "raw" / f"{doc.id}.json").read_text(encoding="utf-8"))
        line, n = pred_line(adapter, doc, record)
        preds.append(line)
        unresolved += n
    write_jsonl(out / "pred.jsonl", preds)
    files = config_files(cfg, config_dir)
    meta.update({
        "config": config_name, "config_sha256": _hash_json(cfg), "config_values": cfg, "tool": cfg["tool"],
        "derived_from": src.name, "derived_utc": started.isoformat(), "harness_commit": _git_commit(),
        "set": ds.name, "gold_sha256": ds.gold_sha256, "derived_from_set": meta["set"],
        "labels_sha256": ds.labels_sha256, "unresolved_total": unresolved, "config_files": files,
        "prompt_sha256": files.get(cfg.get("prompt_file")),
    })
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_score(out / "score.json", run_scorer(ds, out / "pred.jsonl", cfg["tool"]))
    return out


def rescore_from_raw(run_dir: Path, ds: DataSet) -> tuple[dict, bool]:
    """Rebuild pred.jsonl from raw/ without calling the system, score it, and compare with score.json.
    Writes rescore/pred.jsonl and rescore/score.json; returns (new score, identical to the stored one)."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    if meta["set"] != ds.name or meta["gold_sha256"] != ds.gold_sha256:
        raise ValueError(f"run {run_dir.name} was made on {meta['set']} with gold {meta['gold_sha256'][:12]}, "
                         f"not on this {ds.name} ({ds.gold_sha256[:12]})")
    cfg = meta["config_values"]
    adapter = get_adapter_class(cfg["adapter"])(cfg, {})  # only parse() is used: no client, no model, no gold

    preds = []
    for doc in ds:
        record = json.loads((run_dir / "raw" / f"{doc.id}.json").read_text(encoding="utf-8"))
        preds.append(pred_line(adapter, doc, record)[0])
    out = run_dir / "rescore"
    out.mkdir(exist_ok=True)
    write_jsonl(out / "pred.jsonl", preds)
    new = run_scorer(ds, out / "pred.jsonl", meta["tool"])
    write_score(out / "score.json", new)
    old_path = run_dir / "score.json"
    same = old_path.is_file() and old_path.read_bytes() == (out / "score.json").read_bytes()
    return new, same
