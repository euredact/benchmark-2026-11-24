import shutil
from pathlib import Path

import pytest
import yaml

from bench import adapters

FIXTURES = Path(__file__).parent / "fixtures"
REAL_CONFIG = Path(__file__).resolve().parent.parent / "config"

adapters._REGISTRY.setdefault("toy", "toy_adapter:ToyAdapter")

SYSTEMS = {
    "gold": {"configs": {"default": {"adapter": "gold", "tool": "coarse"}}},
    "gold_drop10": {"configs": {"default": {"adapter": "gold", "tool": "coarse", "drop_every": 10}}},
    "toy": {"configs": {
        "default": {"adapter": "toy", "tool": "toy", "backoff_s": 0.0},
        "flaky": {"adapter": "toy", "tool": "toy", "fail_first": 2, "backoff_s": 0.0},
        "outage": {"adapter": "toy", "tool": "toy", "fail_substring": "PESEL", "retries": 2, "backoff_s": 0.0},
        "en_only": {"adapter": "toy", "tool": "toy", "languages": ["en"]},
        "chunked": {"adapter": "toy", "tool": "toy", "max_tokens": 8},
        "unmapped": {"adapter": "toy", "tool": "nobody"},
        "scoped": {"adapter": "toy", "tool": "toy", "backoff_s": 0.0, "exclude_types": ["PHONE_NUMBER"]},
        "scoped_unmatched": {"adapter": "toy", "tool": "toy", "backoff_s": 0.0, "exclude_types": ["NAME"],
                             "exclude_mode": "unmatched"},
    }},
}


@pytest.fixture
def mini_root(tmp_path):
    """A writable copy of the mini set (so tests can tamper with it)."""
    root = tmp_path / "data" / "mini"
    shutil.copytree(FIXTURES / "mini", root)
    return root


@pytest.fixture
def config_dir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    sets = yaml.safe_load((REAL_CONFIG / "sets.yaml").read_text(encoding="utf-8"))
    for cfg in sets["sets"].values():
        cfg.pop("labels_file", None)  # the mini set is scored with its own labels.json
    (d / "sets.yaml").write_text(yaml.safe_dump(sets), encoding="utf-8")
    (d / "systems.yaml").write_text(yaml.safe_dump({"systems": SYSTEMS}), encoding="utf-8")
    return d


@pytest.fixture
def mini(mini_root, config_dir):
    from bench.data import load_set
    return load_set("it360", config_dir=config_dir, root=mini_root)
