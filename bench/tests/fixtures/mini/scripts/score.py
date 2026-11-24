"""Score a tool's predictions against IT-250 gold.

  python3 score.py <gold.jsonl> <pred.jsonl> --tool <name> [--labels labels.json] [--json out.json]

pred.jsonl: one line per document: {"id": "...", "entities": [{"start": int, "end": int, "type": "<native type>"}]}
--tool selects labels.json tool_mappings[<name>] (native type -> coarse). Use --tool coarse if predictions already
carry coarse bucket names, or --tool any to treat every predicted span as a redaction (binary level only).
Unmapped native types are ignored. Predicted ORG spans never count in the binary score.

Levels: binary (redact or not), coarse (bucket must match). Matching: strict (identical offsets) and overlap (any
character overlap). Also char-level precision/recall over redactable characters. Breakdowns: language, genre,
hard vs normal, and per fine type (binary-overlap recall: was it redacted at all).
"""
import argparse, json, os
from collections import defaultdict

def prf(tp_p, n_p, tp_g, n_g):
    p = tp_p / n_p if n_p else 1.0
    r = tp_g / n_g if n_g else 1.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "n_pred": n_p, "n_gold": n_g}

class Acc:
    def __init__(self): self.c = defaultdict(int)
    def add(self, gold, pred, strict, same_type):
        def m(g, p):
            if same_type and g[2] != p[2]: return False
            return (g[0] == p[0] and g[1] == p[1]) if strict else (g[0] < p[1] and p[0] < g[1])
        self.c["tp_g"] += sum(any(m(g, p) for p in pred) for g in gold)
        self.c["tp_p"] += sum(any(m(g, p) for g in gold) for p in pred)
        self.c["n_g"] += len(gold); self.c["n_p"] += len(pred)
    def res(self): return prf(self.c["tp_p"], self.c["n_p"], self.c["tp_g"], self.c["n_g"])

def chars(spans):
    s = set()
    for a, b, *_ in spans: s.update(range(a, b))
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gold"); ap.add_argument("pred")
    ap.add_argument("--tool", required=True)
    ap.add_argument("--labels", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "labels.json"))
    ap.add_argument("--json")
    a = ap.parse_args()
    labels = json.load(open(a.labels, encoding="utf-8"))
    coarse_names = {v["coarse"] for v in labels["fine"].values()}
    if a.tool == "coarse": mapping = {c: c for c in coarse_names}
    elif a.tool == "any": mapping = None
    else: mapping = labels["tool_mappings"][a.tool]
    gold = [json.loads(l) for l in open(a.gold, encoding="utf-8") if l.strip()]
    preds = {}
    for l in open(a.pred, encoding="utf-8"):
        if l.strip():
            r = json.loads(l); preds[r["id"]] = r["entities"]
    missing = [g["id"] for g in gold if g["id"] not in preds]
    acc = defaultdict(Acc)
    ch = defaultdict(lambda: [0, 0, 0])  # covered gold chars, gold chars, pred chars in-gold, pred chars
    chp = defaultdict(lambda: [0, 0])
    fine_rec = defaultdict(lambda: [0, 0])
    for g in gold:
        P = []
        for e in preds.get(g["id"], []):
            if mapping is None: P.append((e["start"], e["end"], "ANY"))
            elif e["type"] in mapping and not str(e["type"]).startswith("_"): P.append((e["start"], e["end"], mapping[e["type"]]))
        Pbin = [p for p in P if p[2] != "ORG"]
        Gred = [(e["start"], e["end"], e["coarse"], e["fine"]) for e in g["entities"] if e["redact"]]
        Gorg = [(e["start"], e["end"], "ORG") for e in g["entities"] if e["coarse"] == "ORG"]
        groups = ["ALL", "lang:" + g["lang"], "genre:" + g["genre"], "hard" if g["hard"] else "normal"]
        for grp in groups:
            acc[(grp, "binary", "strict")].add(Gred, Pbin, True, False)
            acc[(grp, "binary", "overlap")].add(Gred, Pbin, False, False)
            if mapping is not None:
                acc[(grp, "coarse", "strict")].add([x[:3] for x in Gred], Pbin, True, True)
                acc[(grp, "coarse", "overlap")].add([x[:3] for x in Gred], Pbin, False, True)
            gc, pc = chars(Gred), chars(Pbin)
            ch[grp][0] += len(gc & pc); ch[grp][1] += len(gc); chp[grp][0] += len(pc & gc); chp[grp][1] += len(pc)
        if mapping is not None:
            acc[("ALL", "org", "overlap")].add(Gorg, [p for p in P if p[2] == "ORG"], False, False)
        for x in Gred:
            fine_rec[x[3]][1] += 1
            fine_rec[x[3]][0] += any(x[0] < p[1] and p[0] < x[1] for p in Pbin)
    out = {"tool": a.tool, "docs": len(gold), "docs_without_prediction": len(missing), "results": {}, "char": {}, "fine_recall": {}}
    for (grp, lvl, mt), v in sorted(acc.items()):
        out["results"]["%s|%s|%s" % (grp, lvl, mt)] = v.res()
    for grp, (cov, tot, *_ ) in ch.items():
        out["char"][grp] = {"char_recall": round(cov / tot, 4) if tot else 1.0,
                            "char_precision": round(chp[grp][0] / chp[grp][1], 4) if chp[grp][1] else 1.0}
    for f, (h, n) in sorted(fine_rec.items()):
        out["fine_recall"][f] = {"recall": round(h / n, 4), "n": n, "coarse": labels["fine"][f]["coarse"]}
    print("# %s on IT-250 (%d docs, %d without prediction)\n" % (a.tool, len(gold), len(missing)))
    print("| group | level | match | P | R | F1 |\n|---|---|---|---|---|---|")
    for k, v in out["results"].items():
        grp, lvl, mt = k.split("|")
        if grp == "ALL" or (lvl == "binary" and mt == "overlap"):
            print("| %s | %s | %s | %.3f | %.3f | %.3f |" % (grp, lvl, mt, v["precision"], v["recall"], v["f1"]))
    print("\n| group | char P | char R |\n|---|---|---|")
    for grp, v in sorted(out["char"].items()): print("| %s | %.3f | %.3f |" % (grp, v["char_precision"], v["char_recall"]))
    print("\n| fine type | coarse | n | redacted (overlap recall) |\n|---|---|---|---|")
    for f, v in sorted(out["fine_recall"].items(), key=lambda kv: (kv[1]["coarse"], kv[0])):
        print("| %s | %s | %d | %.3f |" % (f, v["coarse"], v["n"], v["recall"]))
    sp = [v for f, v in out["fine_recall"].items() if v["coarse"] in ("SPECIAL", "CRIMINAL")]
    if sp:
        n = sum(v["n"] for v in sp); h = sum(v["recall"] * v["n"] for v in sp)
        print("\n**GDPR Art. 9/10 recall (overlap): %.3f over %d spans**" % (h / n, n))
        out["art9_10_recall"] = round(h / n, 4)
    if a.json: json.dump(out, open(a.json, "w"), indent=1)

if __name__ == "__main__":
    main()
