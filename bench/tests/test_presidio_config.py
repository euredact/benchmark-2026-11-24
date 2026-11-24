"""The Presidio YAML extensions: checksum validators, and every recognizer in tuned.yaml builds and compiles."""

from pathlib import Path

import pytest
import yaml

from bench.adapters.presidio import VALIDATORS

CONFIG = Path(__file__).resolve().parent.parent / "config" / "presidio"


@pytest.mark.parametrize("name,good,bad", [
    ("pesel", "44051401458", "44051401459"),          # PESEL check digit
    ("bsn", "111222333", "111222334"),                # Dutch 11-proof
    ("be_rrn", "85.07.30-033.28", "85.07.30-033.29"),  # mod 97, born before 2000
    ("be_rrn", "00.01.01-001.05", "00.01.01-001.06"),  # mod 97 with the 2 prefix, born 2000 or later
    ("fr_nir", "1 85 05 78 006 084 91", "1 85 05 78 006 084 92"),
    ("luhn", "4111 1111 1111 1111", "4111 1111 1111 1112"),
])
def test_validators(name, good, bad):
    assert VALIDATORS[name](good) and not VALIDATORS[name](bad)


def test_default_yaml_uses_no_extensions():
    """default.yaml is Presidio as shipped: none of the optional keys may appear in it."""
    cfg = yaml.safe_load((CONFIG / "default.yaml").read_text(encoding="utf-8"))
    assert set(cfg) == {"models", "score_threshold"}


def test_tuned_recognizers_build_and_match():
    pytest.importorskip("presidio_analyzer")
    from presidio_analyzer import RecognizerRegistry

    from bench.adapters.presidio import PresidioAdapter, _pattern_recognizer

    cfg = yaml.safe_load((CONFIG / "tuned.yaml").read_text(encoding="utf-8"))
    for spec in cfg["recognizers"]:
        assert set(spec) <= {"name", "entity", "languages", "patterns", "deny_list", "context", "case_sensitive", "validator"}
        assert not spec.get("validator") or spec["validator"] in VALIDATORS
        for lang in spec.get("languages", cfg["models"]):
            _pattern_recognizer(spec, lang)  # compiles every pattern
    registry = RecognizerRegistry(supported_languages=["nl"])
    registry.load_predefined_recognizers(languages=["nl"])
    PresidioAdapter._customise(registry, cfg, "nl")
    names = {r.name for r in registry.recognizers}
    assert "DateRecognizer" not in names and "nl_bsn_nl" in names

    bsn = next(r for r in registry.recognizers if r.name == "nl_bsn_nl")
    text = "BSN: 111222333, ander nummer BSN 111222334"
    hits = [text[r.start:r.end] for r in bsn.analyze(text, ["NATIONAL_ID"])]
    assert hits == ["111222333"]  # the label is not part of the span, and the failing checksum is dropped
