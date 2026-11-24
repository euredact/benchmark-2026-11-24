"""GLiNER2 span extraction (fastino/gliner2-privacy-filter-PII-multi, "GLiNER2-PII"), local.

The label list comes from `labels_file` (config/); the labels are the native types. GLiNER2 puts the label prompt
into the same 512-token sequence as the text, so windows are measured with GLiNER2's own processor (prompt included).
The model is called at `call_threshold` (a floor at or below `threshold`) and `parse` keeps spans at `threshold`:
GLiNER2 picks spans greedily by score, so a lower floor never changes the spans above the threshold (checked on
IT-250 windows), and thresholds can be tuned from raw/ without running the model.

Config: `model`, `revision` (pinned), `labels_file`, `threshold`, `call_threshold`, `max_input_tokens`.
"""

from __future__ import annotations

import importlib.metadata

import yaml

from bench.adapters.base import Adapter, Parsed, Span
from bench.chunk import merge_spans, shift, split
from bench.data import get_config_dir


class GLiNER2Adapter(Adapter):
    name = "gliner2"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self.max_input_tokens = config.get("max_input_tokens", 512)
        self._model = self._schema = self._label_list = None

    def _labels(self) -> list[str]:
        if self._label_list is None:
            path = get_config_dir() / self.config["labels_file"]
            self._label_list = yaml.safe_load(path.read_text(encoding="utf-8"))["labels"]
        return self._label_list

    def _load(self):
        if self._model is None:
            from gliner2 import GLiNER2

            self._model = GLiNER2.from_pretrained(self.config["model"], revision=self.config["revision"])
            self._schema = self._model.create_schema().entities(self._labels())
        return self._model

    def _count(self, text: str) -> int:
        return len(self._model.processor.transform_record(text, self._schema).input_ids)

    def versions(self) -> dict[str, str]:
        out = {p: importlib.metadata.version(p) for p in ("gliner2", "torch", "transformers")}
        out[self.config["model"]] = self.config["revision"]
        return out

    def call(self, text, lang):
        model = self._load()
        floor = min(self.config.get("call_threshold", 0.3), self.config.get("threshold", 0.5))
        windows = split(text, self.max_input_tokens, self._count)
        raw = []
        for w in windows:
            r = model.extract_entities(text[w.start:w.end], self._labels(), threshold=floor,
                                       include_confidence=True, include_spans=True)
            ents = [{"label": label, "start": e["start"], "end": e["end"], "confidence": round(e["confidence"], 6)}
                    for label, found in r["entities"].items() for e in found]
            raw.append({"window": [w.start, w.end], "threshold": floor,
                        "entities": sorted(ents, key=lambda e: (e["start"], e["end"], e["label"]))})
        version = f"{self.config['model']}@{self.config['revision'][:12]}"
        return raw, {"windows": len(windows)}, version

    def parse(self, raw, text, lang):
        threshold = self.config.get("threshold", 0.5)
        spans = []
        for win in raw:
            found = [Span(e["start"], e["end"], e["label"], e["confidence"])
                     for e in win["entities"] if e["confidence"] >= threshold]
            spans.extend(shift(found, win["window"][0]))
        return Parsed(merge_spans(spans))
