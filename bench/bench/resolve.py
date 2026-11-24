"""Map language-model quotes back to document offsets.

Language models return `[{text, type}, ...]` in reading order rather than offsets (they count characters badly).
Each quote is searched forward from the end of the previous match; failing that, the first occurrence not already
used by another quote. Quotes that cannot be found are returned as `unresolved` (they count as missed predictions
and are reported per system), never dropped silently.
"""

from __future__ import annotations

from bench.adapters.base import Parsed, Span


def _occurrences(text: str, quote: str) -> list[int]:
    out, i = [], text.find(quote)
    while i != -1:
        out.append(i)
        i = text.find(quote, i + 1)
    return out


def resolve_quotes(text: str, items: list[dict]) -> Parsed:
    spans: list[Span] = []
    unresolved: list[dict] = []
    used: set[tuple[int, int]] = set()
    cursor = 0
    for item in items:
        quote, typ = item.get("text"), item.get("type")
        if not isinstance(quote, str) or not isinstance(typ, str) or not quote.strip():
            unresolved.append({"item": item, "reason": "malformed"})
            continue
        quote = quote.strip()
        start = text.find(quote, cursor)
        if start == -1 or (start, start + len(quote)) in used:
            start = next((o for o in _occurrences(text, quote) if (o, o + len(quote)) not in used), -1)
        if start == -1:
            unresolved.append({"item": item, "reason": "not_found"})
            continue
        end = start + len(quote)
        used.add((start, end))
        spans.append(Span(start, end, typ))
        cursor = end
    return Parsed(spans=spans, unresolved=len(unresolved), unresolved_quotes=unresolved)
