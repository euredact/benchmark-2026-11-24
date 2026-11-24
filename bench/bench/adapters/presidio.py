"""Microsoft Presidio analyzer, local. One engine per language, built on first use; only one kept in memory.

Config (systems.yaml): `presidio_file`, a YAML under config/ with `models` (spaCy model per language) and
`score_threshold`. Everything else in the YAML is optional and only Presidio's own mechanisms (the `tuned` config):
  ner                 NerModelConfiguration fields (`labels_to_ignore`, `model_to_presidio_entity_mapping`, ...)
  remove_recognizers  predefined recognizers to drop, by name
  builtin             predefined recognizers to add for other languages: [{name: <class>, languages: [..]}]
  phone_regions       regions for Presidio's PhoneRecognizer (replaces its default regions)
  allow_list          values never reported (analyze(allow_list=...)); allow_list_match: exact (default) or regex
  recognizers         PatternRecognizers: name, entity, languages (default: all), patterns [{name, regex, score}],
                      deny_list, context, case_sensitive, validator (one of VALIDATORS)
"""

from __future__ import annotations

import importlib.metadata

import yaml

from bench.adapters.base import Adapter, Parsed, Span
from bench.data import get_config_dir


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _pesel(s: str) -> bool:
    d = _digits(s)
    return len(d) == 11 and (10 - sum(int(a) * w for a, w in zip(d, (1, 3, 7, 9, 1, 3, 7, 9, 1, 3))) % 10) % 10 == int(d[10])


def _bsn(s: str) -> bool:  # Dutch citizen service number: the 11-proof
    d = _digits(s)
    return len(d) == 9 and (sum(int(a) * w for a, w in zip(d, range(9, 1, -1))) - int(d[8])) % 11 == 0


def _be_rrn(s: str) -> bool:  # Belgian national register number: 97 - (first 9 digits mod 97), also with 2 prefixed for 2000+
    d = _digits(s)
    if len(d) != 11:
        return False
    return int(d[9:]) in (97 - int(d[:9]) % 97, 97 - int("2" + d[:9]) % 97)


def _fr_nir(s: str) -> bool:  # French social security number: key = 97 - (13 digits mod 97); Corsica 2A/2B as 19/18
    t = "".join(c for c in s.upper() if c.isalnum()).replace("2A", "19").replace("2B", "18")
    return len(t) == 15 and t.isdigit() and int(t[13:]) == 97 - int(t[:13]) % 97


def _luhn(s: str) -> bool:
    d = [int(c) for c in _digits(s)][::-1]
    return len(d) >= 12 and sum(x if i % 2 == 0 else (x * 2 - 9 if x * 2 > 9 else x * 2) for i, x in enumerate(d)) % 10 == 0


VALIDATORS = {"pesel": _pesel, "bsn": _bsn, "be_rrn": _be_rrn, "fr_nir": _fr_nir, "luhn": _luhn}


def _pattern_recognizer(spec: dict, lang: str):
    """A PatternRecognizer from a YAML spec; a `validator` drops matches that fail the checksum."""
    import regex as re
    from presidio_analyzer import Pattern, PatternRecognizer

    validator = VALIDATORS[spec["validator"]] if spec.get("validator") else None

    class _Recognizer(PatternRecognizer):
        def validate_result(self, pattern_text):
            return validator(pattern_text) if validator else None

    flags = re.DOTALL | re.MULTILINE | (0 if spec.get("case_sensitive") else re.IGNORECASE)
    return _Recognizer(
        supported_entity=spec["entity"], name=f"{spec['name']}_{lang}", supported_language=lang,
        patterns=[Pattern(p["name"], p["regex"], p["score"]) for p in spec.get("patterns", [])] or None,
        deny_list=spec.get("deny_list") or None, context=spec.get("context") or None, global_regex_flags=flags)


class PresidioAdapter(Adapter):
    name = "presidio"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self._settings = None
        self._engine = None
        self._engine_lang = None

    def _load_settings(self) -> dict:
        if self._settings is None:
            path = get_config_dir() / self.config["presidio_file"]
            self._settings = yaml.safe_load(path.read_text(encoding="utf-8"))
        return self._settings

    def _engine_for(self, lang: str):
        if self._engine_lang != lang:
            from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            cfg = self._load_settings()
            model = cfg["models"][lang]
            self._engine = None  # release the previous language's spaCy model first
            nlp_configuration = {"nlp_engine_name": "spacy", "models": [{"lang_code": lang, "model_name": model}]}
            if cfg.get("ner"):
                nlp_configuration["ner_model_configuration"] = cfg["ner"]
            nlp = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
            registry = RecognizerRegistry(supported_languages=[lang])
            registry.load_predefined_recognizers(languages=[lang], nlp_engine=nlp)
            self._customise(registry, cfg, lang)
            self._engine = AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=[lang])
            self._engine_lang = lang
        return self._engine

    @staticmethod
    def _customise(registry, cfg: dict, lang: str) -> None:
        """Apply the optional YAML keys (none in default.yaml, so the shipped behaviour is untouched)."""
        from presidio_analyzer import predefined_recognizers as pre

        for name in cfg.get("remove_recognizers", []):
            registry.remove_recognizer(name, language=lang)
        if cfg.get("phone_regions"):
            registry.remove_recognizer("PhoneRecognizer", language=lang)
            registry.add_recognizer(pre.PhoneRecognizer(supported_language=lang, supported_regions=cfg["phone_regions"]))
        for b in cfg.get("builtin", []):
            if lang in b["languages"]:
                registry.add_recognizer(getattr(pre, b["name"])(supported_language=lang))
        for spec in cfg.get("recognizers", []):
            if lang in spec.get("languages", cfg["models"]):
                registry.add_recognizer(_pattern_recognizer(spec, lang))

    def versions(self) -> dict[str, str]:
        out = {p: importlib.metadata.version(p) for p in ("presidio-analyzer", "spacy")}
        for model in self._load_settings()["models"].values():
            out[model] = importlib.metadata.version(model)
        return out

    def call(self, text, lang):
        cfg = self._load_settings()
        extra = {"allow_list": cfg["allow_list"], "allow_list_match": cfg.get("allow_list_match", "exact")} \
            if cfg.get("allow_list") else {}
        results = self._engine_for(lang).analyze(
            text=text, language=lang, score_threshold=cfg.get("score_threshold"), **extra)
        raw = [{"start": r.start, "end": r.end, "entity_type": r.entity_type, "score": r.score,
                "recognizer": (r.recognition_metadata or {}).get("recognizer_name")}
               for r in sorted(results, key=lambda r: (r.start, r.end, r.entity_type))]
        model = self._load_settings()["models"][lang]
        version = f"presidio-analyzer {importlib.metadata.version('presidio-analyzer')}; {model} " \
                  f"{importlib.metadata.version(model)}"
        return raw, {}, version

    def parse(self, raw, text, lang):
        return Parsed([Span(r["start"], r["end"], r["entity_type"], r["score"]) for r in raw])
