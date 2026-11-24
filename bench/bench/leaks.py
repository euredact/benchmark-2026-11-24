"""Leak view: what a redaction would still show, and what it removed that it should not have.

Computed by the harness beside score.py's output (score.py's P/R/F1 stay the reference numbers). It follows
score.py's binary conventions: gold spans with `redact: true` only; predicted types mapped through the tool's
tool_mappings (`coarse`: bucket names; `any`: every span); predicted ORG spans are not redactions.

Per gold span, over its letters and digits only (so "Jan" + "Peeters" predicted separately still mask "Jan Peeters",
and in an already masked "*****9823" only "9823" can leak: spaces, punctuation and mask characters reveal nothing
on their own). A span with no letter or digit has nothing to leak and counts as masked:
  - masked: all characters covered;
  - partial leak: at least PARTIAL_MIN_COVERAGE (75%) covered, but not all: mostly hidden, a remainder shows;
  - complete leak: less than 75% covered; `uncovered` counts the complete leaks with no character covered at all.
Per predicted span:
  - over-redaction: overlaps no redactable gold span (`touches_org`: it overlaps a gold ORGANISATION, which is
    annotated but never redacted).
Characters (letters and digits): leaked = gold characters not covered; over-redacted = predicted characters outside every
gold span.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PARTIAL_MIN_COVERAGE = 0.75  # below this share of a span's letters and digits covered, the span counts as leaked


def _mapping(labels: dict, tool: str) -> dict | None:
    if tool == "any":
        return None
    if tool == "coarse":
        return {v["coarse"]: v["coarse"] for v in labels["fine"].values()}
    return labels["tool_mappings"][tool]


def _redactions(entities: list[dict], mapping: dict | None) -> list[tuple[int, int]]:
    out = []
    for e in entities:
        if mapping is None:
            out.append((e["start"], e["end"]))
        elif e["type"] in mapping and not str(e["type"]).startswith("_") and mapping[e["type"]] != "ORG":
            out.append((e["start"], e["end"]))
    return out


def _chars(text: str, spans) -> set[int]:
    # a span may end past the text (a decoder that counts one character too many at the very end): clamp it
    return {i for s, e in spans for i in range(max(s, 0), min(e, len(text))) if text[i].isalnum()}


def _ratio(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def leak_report(gold_path: Path, pred_path: Path, labels: dict, tool: str) -> dict:
    mapping = _mapping(labels, tool)
    preds = {}
    with open(pred_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                preds[r["id"]] = r["entities"]

    groups: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    fine: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    docs = {"n": 0, "with_complete_leak": 0, "with_any_leak": 0, "with_over_redaction": 0}
    with open(gold_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            g = json.loads(line)
            text = g["text"]
            gold = [e for e in g["entities"] if e["redact"]]
            orgs = [(e["start"], e["end"]) for e in g["entities"] if e["coarse"] == "ORG"]
            red = _redactions(preds.get(g["id"], []), mapping)
            covered = _chars(text, red)
            gold_chars = _chars(text, [(e["start"], e["end"]) for e in gold])
            keys = ["ALL", f"lang:{g['lang']}", "hard" if g["hard"] else "normal"]
            any_complete = any_leak = False
            for e in gold:
                span_chars = _chars(text, [(e["start"], e["end"])])
                hit = len(span_chars & covered)
                if hit == len(span_chars):
                    state = "masked"
                elif hit >= PARTIAL_MIN_COVERAGE * len(span_chars):
                    state = "partial_leak"
                else:
                    state = "complete_leak"
                any_complete |= state == "complete_leak"
                any_leak |= state != "masked"
                group_keys = keys + (["ART9_10"] if e["coarse"] in ("SPECIAL", "CRIMINAL") else [])
                for counts in [groups[k] for k in group_keys] + [fine[e["fine"]]]:
                    counts["gold_spans"] += 1
                    counts[state] += 1
                    counts["uncovered"] += hit == 0
            over = 0
            for s, e in red:
                if not any(s < ge["end"] and ge["start"] < e for ge in gold):
                    over += 1
                    for k in keys:
                        groups[k]["over_redactions"] += 1
                        if any(s < oe and os_ < e for os_, oe in orgs):
                            groups[k]["over_redactions_touching_org"] += 1
            for k in keys:
                groups[k]["pred_spans"] += len(red)
                groups[k]["gold_chars"] += len(gold_chars)
                groups[k]["leaked_chars"] += len(gold_chars - covered)
                groups[k]["pred_chars"] += len(covered)
                groups[k]["over_redacted_chars"] += len(covered - gold_chars)
            docs["n"] += 1
            docs["with_complete_leak"] += any_complete
            docs["with_any_leak"] += any_leak
            docs["with_over_redaction"] += over > 0

    def summarise(c: dict) -> dict:
        out = {k: c.get(k, 0) for k in ("gold_spans", "masked", "partial_leak", "complete_leak", "uncovered")}
        out["complete_leak_rate"] = _ratio(out["complete_leak"], out["gold_spans"])
        out["partial_leak_rate"] = _ratio(out["partial_leak"], out["gold_spans"])
        if "pred_spans" in c:
            out.update({k: c.get(k, 0) for k in ("pred_spans", "over_redactions", "over_redactions_touching_org")})
            out["over_redaction_rate"] = _ratio(out["over_redactions"], out["pred_spans"])
            out["leaked_char_rate"] = _ratio(c.get("leaked_chars", 0), c.get("gold_chars", 0))
            out["over_redacted_char_rate"] = _ratio(c.get("over_redacted_chars", 0), c.get("pred_chars", 0))
        return out

    return {
        "partial_min_coverage": PARTIAL_MIN_COVERAGE,
        "groups": {k: summarise(v) for k, v in sorted(groups.items())},
        "fine": {k: summarise(v) for k, v in sorted(fine.items())},
        "docs": docs,
    }
