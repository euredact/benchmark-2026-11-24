"""Shared part of the language-model adapters: the versioned prompt in prompts/, JSON output of {text, type} items in
reading order (no offsets), and the resolver that maps each quote to offsets (unresolved quotes are counted).

A provider adapter implements `complete(system, user)` -> (raw response, JSON content string, billed units, model id
as returned). Config: `model` (pinned id), `prompt_file`, `temperature` (default 0).
"""

from __future__ import annotations

import json

from bench.adapters.base import Adapter
from bench.data import PROMPTS_DIR
from bench.resolve import resolve_quotes

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"entities": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "type": {"type": "string"}},
        "required": ["text", "type"], "additionalProperties": False}}},
    "required": ["entities"], "additionalProperties": False,
}


class LLMAdapter(Adapter):
    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self._prompt = None

    def prompt(self) -> str:
        if self._prompt is None:
            self._prompt = (PROMPTS_DIR / self.config["prompt_file"]).read_text(encoding="utf-8")
        return self._prompt

    def complete(self, system: str, user: str):
        raise NotImplementedError

    def call(self, text, lang):
        raw, content, billed, model = self.complete(self.prompt(), text)
        _items(content)  # malformed output is an error (retried, then the document is failed), not an empty answer
        return raw, billed, model

    def content(self, raw) -> str:
        """The JSON string the model answered with, taken from the stored raw response."""
        raise NotImplementedError

    def parse(self, raw, text, lang):
        return resolve_quotes(text, _items(self.content(raw)))


def _items(content: str) -> list[dict]:
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
        raise ValueError("model output is not {\"entities\": [...]}")
    return data["entities"]
