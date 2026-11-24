import hashlib
import json
import shutil

import pytest
import yaml

from bench.run import rescore_from_raw, run
from bench.score import ScoreError


def _read(run_dir, name):
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def _preds(run_dir):
    return [json.loads(line) for line in (run_dir / "pred.jsonl").read_text(encoding="utf-8").splitlines()]


def _results(run_dir):
    return _read(run_dir, "score.json")["result"]["results"]


def test_gold_scores_perfectly(mini, config_dir, tmp_path):
    rd = run("gold", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    assert rd.name.endswith("_gold_default_it360")
    for key in ("ALL|binary|overlap", "ALL|binary|strict", "ALL|coarse|overlap", "ALL|coarse|strict"):
        assert _results(rd)[key]["f1"] == 1.0, key
    assert "| ALL | binary | overlap |" in _read(rd, "score.json")["summary_md"]


def test_gold_with_every_tenth_span_dropped(mini, config_dir, tmp_path):
    rd = run("gold_drop10", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    spans = [e for d in mini for e in sorted(d.entities, key=lambda e: (e["start"], e["end"]))]
    redactable = sum(e["redact"] for e in spans)
    dropped = sum(e["redact"] for e in spans[::10])  # binary recall counts redactable gold only (not ORG)
    assert dropped > 0
    assert _results(rd)["ALL|binary|overlap"]["recall"] == round((redactable - dropped) / redactable, 4)


def test_run_folder_contents(mini, config_dir, tmp_path):
    rd = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    ids = [d.id for d in mini]
    assert [p["id"] for p in _preds(rd)] == ids
    assert sorted(p.stem for p in (rd / "raw").iterdir()) == sorted(ids)
    meta = _read(rd, "meta.json")
    for key in ("system", "config", "config_sha256", "model_versions", "run_started_utc", "set", "gold_sha256",
                "labels_sha256", "prompt_sha256", "per_doc", "billed_units_total", "failed", "unsupported",
                "unresolved_total", "internal_only", "hardware"):
        assert key in meta
    assert meta["model_versions"] == {"toy-1.0": 4}
    assert meta["labels_sha256"] == mini.labels_sha256 == _read(rd, "score.json")["labels_sha256"]
    assert meta["billed_units_total"]["requests"] == 4
    found = {(p["id"], mini.by_id()[p["id"]].text[e["start"]:e["end"]]) for p in _preds(rd) for e in p["entities"]}
    assert ("mini-pl-001", "+48 512 334 901") in found


def test_retries_then_succeeds(mini, config_dir, tmp_path):
    sleeps = []
    rd = run("toy", mini, "flaky", runs_dir=tmp_path / "runs", config_dir=config_dir, sleep=sleeps.append)
    meta = _read(rd, "meta.json")
    assert meta["failed"] == [] and meta["retries_total"] == 2
    assert meta["per_doc"]["mini-en-001"]["attempts"] == 3
    assert len(sleeps) == 2


def test_failed_document_is_kept_and_listed(mini, config_dir, tmp_path):
    rd = run("toy", mini, "outage", runs_dir=tmp_path / "runs", config_dir=config_dir, sleep=lambda s: None)
    meta = _read(rd, "meta.json")
    assert meta["failed"] == ["mini-pl-001"]
    assert meta["per_doc"]["mini-pl-001"]["attempts"] == 3
    assert "simulated outage" in meta["per_doc"]["mini-pl-001"]["errors"][0]
    assert {"id": "mini-pl-001", "entities": []} in _preds(rd)
    assert (rd / "score.json").is_file()


def test_unsupported_languages_are_not_sent(mini, config_dir, tmp_path):
    rd = run("toy", mini, "en_only", runs_dir=tmp_path / "runs", config_dir=config_dir)
    meta = _read(rd, "meta.json")
    assert sorted(meta["unsupported"]) == ["mini-nl-001", "mini-pl-001"]
    assert _read(rd, "raw/mini-nl-001.json")["status"] == "unsupported"
    assert len(_preds(rd)) == 4


def test_chunked_run_equals_unchunked(mini, config_dir, tmp_path):
    whole = run("toy", mini, runs_dir=tmp_path / "a", config_dir=config_dir)
    chunked = run("toy", mini, "chunked", runs_dir=tmp_path / "b", config_dir=config_dir)
    assert _read(chunked, "meta.json")["billed_units_total"]["requests"] > 4
    assert _preds(chunked) == _preds(whole)


def test_missing_tool_mapping_refused_before_any_call(mini, config_dir, tmp_path):
    with pytest.raises(ScoreError, match="tool_mappings\\['nobody'\\]"):
        run("toy", mini, "unmapped", runs_dir=tmp_path / "runs", config_dir=config_dir)
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("system,config", [("toy", "default"), ("toy", "chunked"), ("toy", "outage"),
                                           ("gold_drop10", "default")])
def test_score_from_raw_reproduces_score_json(mini, config_dir, tmp_path, system, config):
    rd = run(system, mini, config, runs_dir=tmp_path / "runs", config_dir=config_dir, sleep=lambda s: None)
    _, same = rescore_from_raw(rd, mini)
    assert same
    assert (rd / "rescore" / "pred.jsonl").read_bytes() == (rd / "pred.jsonl").read_bytes()


def test_from_raw_refuses_another_gold(mini, config_dir, tmp_path, mini_root):
    from bench.data import load_set
    rd = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    gold = mini_root / "gold.jsonl"
    gold.write_text(gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gold"):
        rescore_from_raw(rd, load_set("it360", config_dir=config_dir, root=mini_root))


def test_unmapped_native_type_refused_at_scoring(mini, config_dir, tmp_path, mini_root):
    labels = json.loads((mini_root / "labels.json").read_text(encoding="utf-8"))
    del labels["tool_mappings"]["toy"]["PHONE_NUMBER"]
    (mini_root / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    from bench.data import load_set
    ds = load_set("it360", config_dir=config_dir, root=mini_root)
    with pytest.raises(ScoreError, match=r"lacks native types the run returned: PHONE_NUMBER \(\d+\)"):
        run("toy", ds, runs_dir=tmp_path / "runs", config_dir=config_dir)
    (rd,) = (tmp_path / "runs").iterdir()
    assert (rd / "pred.jsonl").is_file() and (rd / "meta.json").is_file() and not (rd / "score.json").exists()


def test_labels_changed_during_a_run_is_refused(mini, config_dir, tmp_path, mini_root):
    path = mini_root / "labels.json"
    labels = json.loads(path.read_text(encoding="utf-8"))
    labels["tool_mappings"]["toy"]["EXTRA"] = "NAME"  # e.g. a mapping edited while a long run was going
    path.write_text(json.dumps(labels), encoding="utf-8")
    with pytest.raises(ScoreError, match="changed after the set was loaded"):
        run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)


def test_derive_switches_types_off_without_calling_the_system(mini, config_dir, tmp_path):
    from bench.run import derive
    src = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    out = derive(src, mini, "scoped", runs_dir=tmp_path / "runs", config_dir=config_dir)
    types = {e["type"] for p in _preds(out) for e in p["entities"]}
    assert "PHONE_NUMBER" in {e["type"] for p in _preds(src) for e in p["entities"]} and "PHONE_NUMBER" not in types
    meta = _read(out, "meta.json")
    assert meta["derived_from"] == src.name and meta["config"] == "scoped"
    assert (out / "raw").is_dir() and sorted(p.name for p in (out / "raw").iterdir()) == sorted(p.name for p in (src / "raw").iterdir())
    _, same = rescore_from_raw(out, mini)
    assert same


def test_exclude_mode_unmatched_keeps_hits_and_drops_only_over_redaction(mini, config_dir, tmp_path):
    from bench.run import derive
    src = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    out = derive(src, mini, "scoped_unmatched", runs_dir=tmp_path / "runs", config_dir=config_dir)
    before = {(p["id"], e["start"], e["end"]) for p in _preds(src) for e in p["entities"] if e["type"] == "NAME"}
    after = {(p["id"], e["start"], e["end"]) for p in _preds(out) for e in p["entities"] if e["type"] == "NAME"}
    assert ("mini-en-001", 8, 22) in after and ("mini-en-001", 159, 169) in after  # gold persons: still redacted
    assert ("mini-en-001", 0, 7) in before and ("mini-en-001", 0, 7) not in after  # "Dear Ms": over-redaction, dropped
    assert ("mini-en-001", 45, 62) in before and ("mini-en-001", 45, 62) not in after  # overlaps only a gold ORG
    others = lambda d: [(p["id"], e["start"], e["end"], e["type"]) for p in _preds(d) for e in p["entities"] if e["type"] != "NAME"]
    assert others(out) == others(src)
    _, same = rescore_from_raw(out, mini)
    assert same


def test_unknown_exclude_mode_is_refused(mini, config_dir, tmp_path):
    from bench.run import pred_line
    from toy_adapter import ToyAdapter
    doc = next(iter(mini))
    rec = {"status": "ok", "response": ToyAdapter({}).call(doc.text, doc.lang)[0]}
    with pytest.raises(ValueError, match="exclude_mode"):
        pred_line(ToyAdapter({"exclude_types": ["NAME"], "exclude_mode": "some"}), doc, rec)


def test_derive_refuses_a_config_that_changes_the_calls(mini, config_dir, tmp_path):
    from bench.run import derive
    src = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    with pytest.raises(ValueError, match="max_tokens"):
        derive(src, mini, "chunked", runs_dir=tmp_path / "runs", config_dir=config_dir)


def test_parallel_run_gives_the_same_folder_as_a_sequential_one(mini, config_dir, tmp_path):
    one = run("toy", mini, runs_dir=tmp_path / "one", config_dir=config_dir)
    four = run("toy", mini, runs_dir=tmp_path / "four", config_dir=config_dir, workers=4)
    assert _preds(one) == _preds(four) and [p["id"] for p in _preds(four)] == [d.id for d in mini]
    assert _results(one) == _results(four)
    assert sorted(p.name for p in (four / "raw").iterdir()) == sorted(p.name for p in (one / "raw").iterdir())
    assert _read(four, "meta.json")["concurrency"] == {"workers": 4, "max_per_min": None}


def test_parallel_run_keeps_failures_and_retries(mini, config_dir, tmp_path):
    rd = run("toy", mini, "outage", runs_dir=tmp_path / "runs", config_dir=config_dir, sleep=lambda s: None, workers=3)
    assert _read(rd, "meta.json")["failed"] == ["mini-pl-001"]


def test_rate_limiter_spaces_call_starts_across_threads():
    import threading

    from bench.run import RateLimiter

    t = [0.0]
    waits = []

    def sleep(s):
        waits.append(round(s, 6))

    lim = RateLimiter(30, clock=lambda: t[0], sleep=sleep)  # one start every 2 s
    threads = [threading.Thread(target=lim) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(waits) == [2.0, 4.0, 6.0]  # the first starts at once, the others 2 s apart
    t[0] = 100.0
    waits.clear()
    lim()
    assert waits == []  # after a quiet spell the next call is not delayed
    assert RateLimiter(None).interval == 0


def test_derive_onto_another_gold_of_the_same_documents(mini, config_dir, tmp_path, mini_root):
    from bench.data import load_set
    from bench.run import derive
    src = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    other_root = tmp_path / "data" / "mini_regold"
    shutil.copytree(mini_root, other_root)
    gold = [json.loads(l) for l in (other_root / "gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for g in gold:
        g["entities"] = g["entities"][:1]  # another gold over the same texts
    (other_root / "gold.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    sets = yaml.safe_load((config_dir / "sets.yaml").read_text(encoding="utf-8"))
    sets["sets"]["it360_regold"] = sets["sets"]["it360"]
    (config_dir / "sets.yaml").write_text(yaml.safe_dump(sets), encoding="utf-8")
    regold = load_set("it360_regold", config_dir=config_dir, root=other_root)
    with pytest.raises(ValueError, match="pass that set as source"):
        derive(src, regold, "default", runs_dir=tmp_path / "runs", config_dir=config_dir)
    out = derive(src, regold, "default", runs_dir=tmp_path / "runs", config_dir=config_dir, source=mini)
    meta = _read(out, "meta.json")
    assert meta["set"] == "it360_regold" and meta["derived_from_set"] == "it360" and meta["gold_sha256"] == regold.gold_sha256
    assert _preds(out) == _preds(src)
    _, same = rescore_from_raw(out, regold)
    assert same
    # same ids, one text changed (its gold sha256 updated so the set itself loads): refused
    changed = tmp_path / "data" / "mini_text"
    shutil.copytree(other_root, changed)
    g0 = gold[0]
    path = changed / "docs" / g0["lang"] / f"{g0['id']}.txt"
    text = path.read_text(encoding="utf-8") + " extra"
    path.write_text(text, encoding="utf-8")
    g0["text"], g0["sha256"] = text, hashlib.sha256(text.encode("utf-8")).hexdigest()
    (changed / "gold.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    with pytest.raises(ValueError, match="same documents"):
        derive(src, load_set("it360_regold", config_dir=config_dir, root=changed), "default",
               runs_dir=tmp_path / "runs", config_dir=config_dir, source=mini)


def test_reuse_takes_identical_documents_from_an_earlier_run_and_calls_the_rest(mini, config_dir, tmp_path, mini_root):
    from bench.data import load_set
    src = run("toy", mini, runs_dir=tmp_path / "runs", config_dir=config_dir)
    # an extended set: the same documents, one of them changed (its gold sha256 updated so the set loads)
    ext_root = tmp_path / "data" / "mini_ext"
    shutil.copytree(mini_root, ext_root)
    gold = [json.loads(l) for l in (ext_root / "gold.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    g0 = gold[0]
    path = ext_root / "docs" / g0["lang"] / f"{g0['id']}.txt"
    text = path.read_text(encoding="utf-8") + " extra"
    path.write_text(text, encoding="utf-8")
    g0["text"], g0["sha256"] = text, hashlib.sha256(text.encode("utf-8")).hexdigest()
    (ext_root / "gold.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    sets = yaml.safe_load((config_dir / "sets.yaml").read_text(encoding="utf-8"))
    sets["sets"]["it360_ext"] = sets["sets"]["it360"]
    (config_dir / "sets.yaml").write_text(yaml.safe_dump(sets), encoding="utf-8")
    ext = load_set("it360_ext", config_dir=config_dir, root=ext_root)

    out = run("toy", ext, runs_dir=tmp_path / "runs2", config_dir=config_dir, reuse=[(src, mini)])
    meta = _read(out, "meta.json")
    reused = meta["reused"][src.name]
    assert g0["id"] not in reused and len(reused) == len(mini) - 1  # the changed document was called again
    assert all(meta["per_doc"][i]["reused_from"] == src.name for i in reused)
    fresh = run("toy", ext, runs_dir=tmp_path / "runs3", config_dir=config_dir)
    assert _preds(out) == _preds(fresh)  # reused answers give what a fresh run gives
    with pytest.raises(ValueError, match="not a run of toy with this configuration"):
        run("toy", ext, "scoped", runs_dir=tmp_path / "runs4", config_dir=config_dir, reuse=[(src, mini)])
