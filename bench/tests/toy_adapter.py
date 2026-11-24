"""A deterministic offline adapter for the harness tests: regex detector, optional failures and chunking."""

import re

from bench.adapters.base import Adapter, Parsed, Span
from bench.chunk import Window, merge_spans, shift, split

_PATTERNS = {
    "EMAIL_ADDRESS": r"[\w.]+@[\w.]+\w",
    "PHONE_NUMBER": r"\+?\d[\d ]{8,}\d",
    "NAME": r"\b[A-Z][a-zę]+ [A-Z][a-zęó]+\b",
}


def _find(text):
    return [Span(m.start(), m.end(), t, 0.9) for t, p in _PATTERNS.items() for m in re.finditer(p, text)]


class ToyAdapter(Adapter):
    name = "toy"

    def __init__(self, config, context=None):
        super().__init__(config, context)
        self.calls = 0

    def call(self, text, lang):
        self.calls += 1
        if self.config.get("fail_substring") and self.config["fail_substring"] in text:
            raise ConnectionError("simulated outage")
        if self.calls <= self.config.get("fail_first", 0):
            raise TimeoutError("simulated timeout")
        windows = split(text, self.config["max_tokens"]) if self.config.get("max_tokens") else [Window(0, len(text))]
        raw = [{"window": [w.start, w.end],
                "matches": [{"s": s.start, "e": s.end, "label": s.type, "score": s.score}
                            for s in _find(text[w.start:w.end])]}
               for w in windows]
        return raw, {"requests": len(windows), "chars": len(text)}, "toy-1.0"

    def parse(self, raw, text, lang):
        spans = []
        for r in raw:
            found = [Span(m["s"], m["e"], m["label"], m["score"]) for m in r["matches"]]
            spans.extend(shift(found, r["window"][0]))
        return Parsed(merge_spans(spans))
