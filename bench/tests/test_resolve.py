from bench.adapters.base import Span
from bench.resolve import resolve_quotes

TEXT = "Anna met Bob. Later Anna called Bob's sister Cleo, and Anna left."


def test_forward_search_follows_reading_order():
    p = resolve_quotes(TEXT, [{"text": "Anna", "type": "P"}, {"text": "Bob", "type": "P"},
                              {"text": "Anna", "type": "P"}, {"text": "Anna", "type": "P"}])
    starts = [s.start for s in p.spans]
    assert starts == [0, 9, 20, 55]
    assert p.unresolved == 0


def test_out_of_order_quote_falls_back_to_first_unused_occurrence():
    p = resolve_quotes(TEXT, [{"text": "Cleo", "type": "P"}, {"text": "Anna", "type": "P"},
                              {"text": "Bob", "type": "P"}])
    assert p.spans[0] == Span(45, 49, "P")
    assert p.spans[1] == Span(55, 59, "P")  # forward from Cleo
    assert p.spans[2] == Span(9, 12, "P")  # nothing forward: first unused occurrence


def test_unfindable_and_malformed_quotes_are_counted():
    p = resolve_quotes(TEXT, [{"text": "Dave", "type": "P"}, {"type": "P"}, {"text": " Bob ", "type": "P"}])
    assert [s.start for s in p.spans] == [9]
    assert p.unresolved == 2
    assert [u["reason"] for u in p.unresolved_quotes] == ["not_found", "malformed"]


def test_more_quotes_than_occurrences():
    p = resolve_quotes("Cleo and Cleo", [{"text": "Cleo", "type": "P"}] * 3)
    assert [s.start for s in p.spans] == [0, 9]
    assert p.unresolved == 1
