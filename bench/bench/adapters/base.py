"""The one interface every system adapter implements.

An adapter calls its system and translates the output into spans with the system's *native* types. It does not
map types (labels.json does), filter by score (except at its configured threshold) or merge chunks (chunk.py does).

`detect` is split into `call` (talks to the system, returns the raw response) and `parse` (raw -> spans), so a run
can be re-scored from its stored raw responses without calling the system again (`bench score --from-raw`).

Construction must be cheap and offline: create clients, load models and read keys lazily in `call`, so that
`--from-raw` can build the adapter just to `parse`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Span:
    start: int  # Python string index (code points) into the document text
    end: int
    type: str  # the system's native type
    score: float | None = None

    def to_pred(self) -> dict:
        return {"start": self.start, "end": self.end, "type": self.type}


@dataclass
class Parsed:
    spans: list[Span]
    unresolved: int = 0  # language-model quotes that could not be located in the text
    unresolved_quotes: list[dict] = field(default_factory=list)


@dataclass
class AdapterResult:
    spans: list[Span]
    raw: Any  # JSON-serialisable, stored untouched in raw/<doc id>.json
    billed_units: dict[str, float] = field(default_factory=dict)  # e.g. {"input_tokens": 812, "requests": 1}
    latency_s: float = 0.0
    model_version: str | None = None  # as returned by the system, not as requested
    unresolved: int = 0
    unresolved_quotes: list[dict] = field(default_factory=list)


class Adapter:
    name: str = ""
    max_input_tokens: int | None = None
    internal_only: bool = False  # licence or policy keeps this system out of the public report

    def __init__(self, config: dict, context: dict | None = None):
        self.config = config
        self.context = context or {}

    def call(self, text: str, lang: str) -> tuple[Any, dict[str, float], str | None]:
        """Call the system. Returns (raw response, billed units, model version as returned)."""
        raise NotImplementedError

    def parse(self, raw: Any, text: str, lang: str) -> Parsed:
        """Translate a stored raw response into spans. Must be deterministic and must not call the system."""
        raise NotImplementedError

    def preflight(self) -> None:
        """Fail fast before a run starts (missing key, endpoint, package). Must not call the system."""

    def versions(self) -> dict[str, str]:
        """Library and model versions actually loaded or served (recorded in meta.json after the run)."""
        return {}

    def detect(self, text: str, lang: str) -> AdapterResult:
        t0 = time.perf_counter()
        raw, billed, version = self.call(text, lang)
        latency = time.perf_counter() - t0
        parsed = self.parse(raw, text, lang)
        return AdapterResult(
            spans=parsed.spans,
            raw=raw,
            billed_units=billed,
            latency_s=latency,
            model_version=version,
            unresolved=parsed.unresolved,
            unresolved_quotes=parsed.unresolved_quotes,
        )
