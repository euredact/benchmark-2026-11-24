import json

import pytest

from bench.data import IntegrityError, load_set


def test_loads_and_verifies(mini):
    assert len(mini) == 4
    assert {d.lang for d in mini} == {"en", "nl", "pl"}
    assert len(mini.gold_sha256) == 64 and len(mini.labels_sha256) == 64


def test_refuses_changed_document(mini_root, config_dir):
    p = mini_root / "docs" / "en" / "mini-en-002.txt"
    p.write_bytes(p.read_bytes().replace(b"Invoice", b"invoice"))
    with pytest.raises(IntegrityError, match="mini-en-002: sha256"):
        load_set("it360", config_dir=config_dir, root=mini_root)


def test_refuses_missing_document(mini_root, config_dir):
    (mini_root / "docs" / "pl" / "mini-pl-001.txt").unlink()
    with pytest.raises(IntegrityError, match="mini-pl-001: missing"):
        load_set("it360", config_dir=config_dir, root=mini_root)


def test_refuses_gold_offsets_that_do_not_match_text(mini_root, config_dir):
    gold = mini_root / "gold.jsonl"
    rows = [json.loads(line) for line in gold.read_text(encoding="utf-8").splitlines()]
    rows[0]["entities"][0]["start"] += 1
    gold.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(IntegrityError, match="mini-en-001: entity 0 text"):
        load_set("it360", config_dir=config_dir, root=mini_root)


def test_root_comes_from_environment(config_dir, monkeypatch):
    monkeypatch.delenv("BENCH_DATA_DIR", raising=False)
    with pytest.raises(KeyError, match="BENCH_DATA_DIR"):
        load_set("it360", config_dir=config_dir)


def test_unknown_set(config_dir):
    with pytest.raises(KeyError, match="unknown set"):
        load_set("test", config_dir=config_dir)


def _with_labels_file(config_dir, mini_root, edit):
    import yaml
    labels = json.loads((mini_root / "labels.json").read_text(encoding="utf-8"))
    edit(labels)
    (config_dir / "labels").mkdir(exist_ok=True)
    (config_dir / "labels" / "mini.json").write_text(json.dumps(labels), encoding="utf-8")
    sets = yaml.safe_load((config_dir / "sets.yaml").read_text(encoding="utf-8"))
    sets["sets"]["it360"]["labels_file"] = "labels/mini.json"
    (config_dir / "sets.yaml").write_text(yaml.safe_dump(sets), encoding="utf-8")
    return load_set("it360", config_dir=config_dir, root=mini_root)


def test_repo_labels_file_may_add_mappings(mini_root, config_dir):
    ds = _with_labels_file(config_dir, mini_root, lambda L: L["tool_mappings"].update({"new_tool": {"X": "NAME"}}))
    assert ds.labels_path == config_dir / "labels" / "mini.json"
    assert "new_tool" in ds.labels()["tool_mappings"]


def test_repo_labels_file_may_not_change_the_label_set(mini_root, config_dir):
    def edit(L):
        L["fine"]["PERSON"]["coarse"] = "CONTACT"
    with pytest.raises(IntegrityError, match="outside tool_mappings: fine"):
        _with_labels_file(config_dir, mini_root, edit)


def test_repo_labels_file_may_not_change_release_mappings(mini_root, config_dir):
    def edit(L):
        L["tool_mappings"]["toy"]["NAME"] = "ORG"
    with pytest.raises(IntegrityError, match="only additions allowed\\): toy"):
        _with_labels_file(config_dir, mini_root, edit)
