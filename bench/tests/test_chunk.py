import re

import pytest

from bench.adapters.base import Span
from bench.chunk import detect_windows, merge_spans, split, whitespace_tokens

TEXT = (
    "Dear Ms Elara Vintfold,\n\n"
    "Your appointment at Brightmoor Clinic is on 3 March. Please bring your card. "
    "The clinic is on the second floor of the building next to the station.\n\n"
    "If you cannot come, call Tomas Reyk at the front desk before noon. He will rebook the visit.\n\n"
    "Kind regards,\nBrightmoor Clinic"
)


def test_short_text_is_one_window():
    assert [(w.start, w.end) for w in split("a b c", 10)] == [(0, 5)]


@pytest.mark.parametrize("max_tokens", [4, 7, 12, 25])
def test_windows_fit_cover_and_overlap(max_tokens):
    ws = split(TEXT, max_tokens)
    assert len(ws) > 1
    assert ws[0].start == 0 and ws[-1].end == len(TEXT)
    for a, b in zip(ws, ws[1:]):
        assert a.start < b.start <= a.end  # progress, no gap
    for w in ws:
        assert whitespace_tokens(TEXT[w.start:w.end]) <= max_tokens


def test_prefers_paragraph_then_sentence_boundaries():
    ws = split(TEXT, 45)  # the break after paragraph 2 (word 35) lies in the second half of the window
    assert TEXT[: ws[0].end].endswith("\n\n")
    ws = split(TEXT, 30)  # the only paragraph break (word 4) is too early: a sentence break wins
    assert TEXT[: ws[0].end].endswith("card. ")
    ws = split(TEXT, 14)
    assert any(TEXT[: w.end].rstrip().endswith(".") for w in ws[:-1])


def test_custom_tokenizer_is_respected():
    chars = len  # a character "tokenizer"
    for w in split(TEXT, 40, count_tokens=chars):
        assert w.end - w.start <= 40


def test_span_crossing_window_boundary_comes_out_whole():
    # Window ends inside "Tomas Reyk"? Force it: find a max_tokens whose window boundary cuts the name.
    name = "Tomas Reyk"
    s0 = TEXT.index(name)
    gold = Span(s0, s0 + len(name), "PERSON", 0.9)
    for max_tokens in range(4, 30):
        ws = split(TEXT, max_tokens, overlap_tokens=3)
        if any(w.start < gold.end and gold.start < w.end and not (w.start <= gold.start and gold.end <= w.end)
               for w in ws):
            break
    else:
        pytest.fail("no window size cuts the name; adjust the test text")

    def detect(wtext):
        # sees only the part of the name inside the window, as a model would at an edge
        w_start = next(w.start for w in ws if TEXT[w.start:w.end] == wtext)
        lo, hi = max(gold.start, w_start), min(gold.end, w_start + len(wtext))
        return [Span(lo - w_start, hi - w_start, "PERSON", 0.9)] if lo < hi else []

    assert detect_windows(TEXT, ws, detect) == [gold]
    assert TEXT[gold.start:gold.end] == name


def test_merge_unions_same_type():
    out = merge_spans([Span(0, 5, "A", 0.5), Span(3, 9, "A", 0.7), Span(9, 12, "A", 0.1)])
    assert out == [Span(0, 9, "A", 0.7), Span(9, 12, "A", 0.1)]  # touching is not overlapping


def test_merge_conflicting_types_keeps_higher_score():
    out = merge_spans([Span(0, 5, "A", 0.5), Span(3, 9, "B", 0.8), Span(20, 25, "A", None)])
    assert out == [Span(3, 9, "B", 0.8), Span(20, 25, "A", None)]


def test_merge_without_scores_prefers_longer():
    assert merge_spans([Span(0, 4, "A"), Span(2, 10, "B")]) == [Span(2, 10, "B")]


def test_regex_detection_over_many_windows_matches_whole_text():
    def detect(t):
        return [Span(m.start(), m.end(), "CAP", 1.0) for m in re.finditer(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", t)]

    whole = detect(TEXT)
    assert detect_windows(TEXT, split(TEXT, 9, overlap_tokens=3), detect) == whole
