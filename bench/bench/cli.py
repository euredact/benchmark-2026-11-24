"""bench run | score | record | derive

    bench run    --system <name> --set <set> [--config default|tuned] [--workers N] [--max-per-min R]
    bench score  --run <run dir> [--from-raw]
    bench record --system <name> --set <set> [--config default] [--docs id,id,id]
    bench derive --run <run dir> --config <name>     (another config's run from the same raw responses)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench.data import IntegrityError, load_set
from bench.run import RUNS_DIR, derive, record, rescore_from_raw, run
from bench.score import ScoreError, run_scorer, write_score


def _summary(score: dict) -> str:
    return score.get("summary_md") or json.dumps(score["result"], indent=2, ensure_ascii=False)[:4000]


def cmd_run(args) -> int:
    ds = load_set(args.set)
    reuse = []
    for r in args.reuse_from or []:
        reuse.append((Path(r), load_set(json.loads((Path(r) / "meta.json").read_text(encoding="utf-8"))["set"])))
    run_dir = run(args.system, ds, args.config, runs_dir=Path(args.runs_dir), workers=args.workers, reuse=reuse,
                  max_per_min=args.max_per_min)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    print(f"run: {run_dir}")
    print(f"docs {meta['n_docs']}, failed {len(meta['failed'])}, unsupported {len(meta['unsupported'])}, "
          f"unresolved quotes {meta['unresolved_total']}")
    if meta["failed"]:
        print("failed: " + ", ".join(meta["failed"]))
    print(_summary(json.loads((run_dir / "score.json").read_text(encoding="utf-8"))))
    return 0


def cmd_score(args) -> int:
    run_dir = Path(args.run)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    ds = load_set(meta["set"])
    if args.from_raw:
        score, same = rescore_from_raw(run_dir, ds)
        print(_summary(score))
        print("from raw: identical to score.json" if same else "from raw: DIFFERS from score.json (see rescore/)")
        return 0 if same else 1
    score = run_scorer(ds, run_dir / "pred.jsonl", meta["tool"])
    write_score(run_dir / "score.json", score)
    print(_summary(score))
    return 0


def cmd_record(args) -> int:
    ds = load_set(args.set)
    docs = args.docs.split(",") if args.docs else None
    for path in record(args.system, ds, args.config, docs):
        rec = json.loads(path.read_text(encoding="utf-8"))
        print(f"{path}: {rec['record']['status']}, {len(rec['pred']['entities'])} spans")
    return 0


def cmd_derive(args) -> int:
    meta = json.loads((Path(args.run) / "meta.json").read_text(encoding="utf-8"))
    ds = load_set(args.set or meta["set"])
    source = load_set(meta["set"]) if ds.name != meta["set"] else None
    out = derive(Path(args.run), ds, args.config or meta["config"], runs_dir=Path(args.runs_dir), source=source)
    print(f"run: {out}")
    print(_summary(json.loads((out / "score.json").read_text(encoding="utf-8"))))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bench", description="euRedact competitive benchmark harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a system on a set and write a run folder")
    r.add_argument("--system", required=True)
    r.add_argument("--set", required=True)
    r.add_argument("--config", default="default")
    r.add_argument("--runs-dir", default=str(RUNS_DIR))
    r.add_argument("--workers", type=int, default=1, help="documents in flight at once (default 1)")
    r.add_argument("--max-per-min", type=float, default=None, help="cap on calls started per minute, retries included")
    r.add_argument("--reuse-from", action="append", metavar="RUN",
                   help="an earlier run of the same system and config: identical documents reuse its answers (repeatable)")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="(re)score a run folder with the set's score.py")
    s.add_argument("--run", required=True)
    s.add_argument("--from-raw", action="store_true", help="rebuild pred.jsonl from raw/ and compare with score.json")
    s.set_defaults(func=cmd_score)

    c = sub.add_parser("record", help="record a system's responses on a few documents for the adapter tests")
    c.add_argument("--system", required=True)
    c.add_argument("--set", required=True)
    c.add_argument("--config", default="default")
    c.add_argument("--docs", help="comma-separated ids (default: the set's recording_docs)")
    c.set_defaults(func=cmd_record)

    d = sub.add_parser("derive", help="derive another config's run from an existing run's raw responses (no system call)")
    d.add_argument("--run", required=True)
    d.add_argument("--config", help="the config to derive (default: the run's own)")
    d.add_argument("--set", help="score on another set with the same documents, e.g. another gold (default: the run's own)")
    d.add_argument("--runs-dir", default=str(RUNS_DIR))
    d.set_defaults(func=cmd_derive)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (IntegrityError, ScoreError, KeyError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
