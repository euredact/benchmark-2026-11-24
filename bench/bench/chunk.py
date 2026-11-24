"""The one splitter for every system with an input limit, and the span merge that undoes it.

`split` produces overlapping windows of at most `max_tokens` (measured with the system's own tokenizer via
`count_tokens`), preferring to break on a paragraph boundary, then a sentence boundary, then whitespace.
`detect_windows` runs a detector per window, shifts its spans back to document offsets and merges them:
overlapping spans of the same native type are unioned; between conflicting types the higher-scoring span wins.

euRedact does not use this: it goes through its own production segmentation.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Callable

from bench.adapters.base import Span

TokenCounter = Callable[[str], int]

_PARA = re.compile(r"\n[ \t]*\n\s*")
_SENT = re.compile(r"(?<=[.!?…:;])[\"')\]»”]*\s+|\n\s*")
_WORD = re.compile(r"\s+")


def whitespace_tokens(text: str) -> int:
    """Fallback counter when a system has no local tokenizer. Give such adapters a safety margin."""
    return len(text.split())


@dataclass(frozen=True)
class Window:
    start: int
    end: int


def _breaks(pattern: re.Pattern, text: str) -> list[int]:
    """Positions where a window may end (just after the separator)."""
    return [m.end() for m in pattern.finditer(text)]


def split(text: str, max_tokens: int, count_tokens: TokenCounter = whitespace_tokens,
          overlap_tokens: int | None = None) -> list[Window]:
    if max_tokens < 2:
        raise ValueError("max_tokens must be at least 2")
    if overlap_tokens is None:
        overlap_tokens = max(1, max_tokens // 8)
    n = len(text)
    if n == 0:
        return []
    if count_tokens(text) <= max_tokens:
        return [Window(0, n)]

    para, sent, word = _breaks(_PARA, text), _breaks(_SENT, text), _breaks(_WORD, text)
    windows: list[Window] = []
    start = 0
    while start < n:
        hard = _max_end(text, start, max_tokens, count_tokens)
        if hard >= n:
            windows.append(Window(start, n))
            break
        end = _best_break(start, hard, para, sent, word)
        windows.append(Window(start, end))
        start = _next_start(text, start, end, overlap_tokens, count_tokens, word)
    return windows


def _max_end(text: str, start: int, max_tokens: int, count: TokenCounter) -> int:
    """Largest end with count(text[start:end]) <= max_tokens (binary search; counts grow with length)."""
    lo, hi = start + 1, len(text)
    if count(text[start:hi]) <= max_tokens:
        return hi
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count(text[start:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _last_in(breaks: list[int], lo: int, hi: int) -> int | None:
    """Last break b with lo < b <= hi."""
    i = bisect_right(breaks, hi) - 1
    return breaks[i] if i >= 0 and breaks[i] > lo else None


def _best_break(start: int, hard: int, para: list[int], sent: list[int], word: list[int]) -> int:
    half = start + (hard - start) // 2  # don't give up more than half a window for a nicer boundary
    for breaks in (para, sent):
        b = _last_in(breaks, half, hard)
        if b is not None:
            return b
    b = _last_in(word, start, hard)
    return b if b is not None else hard


def _next_start(text: str, start: int, end: int, overlap: int, count: TokenCounter, word: list[int]) -> int:
    """Start of the next window: about `overlap` tokens before `end`, snapped forward to a word start."""
    lo, hi = start + 1, end
    while lo < hi:  # smallest s in (start, end] with count(text[s:end]) <= overlap
        mid = (lo + hi) // 2
        if count(text[mid:end]) <= overlap:
            hi = mid
        else:
            lo = mid + 1
    i = bisect_right(word, lo - 1)
    snapped = word[i] if i < len(word) and word[i] < end else lo
    return max(start + 1, min(snapped, end))


def shift(spans: list[Span], offset: int) -> list[Span]:
    return [Span(s.start + offset, s.end + offset, s.type, s.score) for s in spans]


def _max_score(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    return a if b is None else max(a, b)


def merge_spans(spans: list[Span]) -> list[Span]:
    """Union overlapping same-type spans, then resolve overlaps between types: higher score wins
    (a missing score counts as lowest), then the longer span, then the earlier one."""
    by_type: dict[str, list[Span]] = {}
    for s in spans:
        by_type.setdefault(s.type, []).append(s)

    unioned: list[Span] = []
    for typ, group in by_type.items():
        group.sort(key=lambda s: (s.start, s.end))
        cur = group[0]
        for s in group[1:]:
            if s.start < cur.end:
                cur = Span(cur.start, max(cur.end, s.end), typ, _max_score(cur.score, s.score))
            else:
                unioned.append(cur)
                cur = s
        unioned.append(cur)

    def rank(s: Span):
        return (-(s.score if s.score is not None else float("-inf")), -(s.end - s.start), s.start, s.type)

    kept: list[Span] = []
    for s in sorted(unioned, key=rank):
        if all(s.end <= k.start or k.end <= s.start for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: (s.start, s.end, s.type))


def detect_windows(text: str, windows: list[Window], detect: Callable[[str], list[Span]]) -> list[Span]:
    """Run `detect` on each window's text and return merged spans in document offsets."""
    out: list[Span] = []
    for w in windows:
        out.extend(shift(detect(text[w.start:w.end]), w.start))
    return merge_spans(out)
