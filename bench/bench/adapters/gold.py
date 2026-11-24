"""Replays a set's gold entities as predictions, with gold types. Harness and scorer sanity check, not a system.

The type is the gold entity's `type_field` (default `coarse`, to be scored with `--tool coarse`). Expected on IT-250:
1.000; with `drop_every: 10` (every 10th gold span in set order, by offset within a document, starting with the
first) binary-overlap recall 0.901. The README's 0.899 is from a 10% drop whose rule it does not record.
"""

from __future__ import annotations

from bench.adapters.base import Adapter, Parsed, Span
from bench.data import sha256_bytes


class GoldAdapter(Adapter):
    name = "gold"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self._by_text = None
        self._counter = 0  # running index over the set's gold spans, so drop_every spans documents

    def call(self, text, lang):
        if self._by_text is None:
            self._by_text = {sha256_bytes(d.text.encode("utf-8")): d for d in self.context["dataset"]}
        doc = self._by_text[sha256_bytes(text.encode("utf-8"))]
        drop_every = self.config.get("drop_every")
        type_field = self.config.get("type_field", "coarse")
        ents = []
        for e in sorted(doc.entities, key=lambda e: (e["start"], e["end"])):
            if not (drop_every and self._counter % drop_every == 0):
                ents.append({"start": e["start"], "end": e["end"], "type": e[type_field]})
            self._counter += 1
        return {"doc_id": doc.id, "entities": ents}, {"spans": len(ents)}, "gold"

    def parse(self, raw, text, lang):
        return Parsed([Span(e["start"], e["end"], e["type"]) for e in raw["entities"]])
