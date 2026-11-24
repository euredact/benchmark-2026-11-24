"""The bards.ai decoder (a port of the model cards' pii_detector.py) on hand-made raw output."""

from bench.adapters.base import Span
from bench.adapters.bards import decode

TYPES = ["ACCOUNT_IDENTIFIER", "EMAIL_ADDRESS", "PERSON_NAME", "PHONE_NUMBER"]
O = len(TYPES)


def tok(text, piece, probs, b=0.0, start=0):
    """A token for the first occurrence of `piece` at or after `start`: {type index: p}, B mass."""
    return [text.index(piece, start), {str(k): v for k, v in probs.items()}, b]


def raw(*windows):
    return {"types": TYPES, "windows": [{"window": [0, 0], "tokens": list(w)} for w in windows]}


def test_word_label_is_mean_over_its_tokens_and_words_merge():
    t = "Call Jan Peeters-Smit now."
    r = raw([tok(t, "Call", {O: 1.0}),
             tok(t, "Jan", {2: 0.9, O: 0.1}, b=0.9), tok(t, "Pee", {2: 0.8, O: 0.2}, b=0.1),
             tok(t, "ters", {2: 0.2, O: 0.8}), tok(t, "-Smit", {2: 0.7, O: 0.3}),  # word mean 0.5667 > O
             tok(t, "now", {O: 1.0})])
    assert decode(t, r) == [Span(5, 21, "PERSON_NAME", round((0.9 + (0.8 + 0.2 + 0.7) / 3) / 2, 6))]


def test_a_new_b_starts_a_new_span():
    t = "Jan Piet"
    r = raw([tok(t, "Jan", {2: 1.0}, b=1.0), tok(t, "Piet", {2: 1.0}, b=0.9)])
    assert [(s.start, s.end) for s in decode(t, r)] == [(0, 3), (4, 8)]


def test_quotes_split_words_and_edge_punctuation_is_trimmed():
    t = 'user = "zbrennan", (bill.ashworth).'
    r = raw([tok(t, "user", {O: 1.0}), tok(t, "zbrennan", {2: 0.9, O: 0.1}, b=0.9),
             tok(t, "bill", {2: 0.8, O: 0.2}, b=0.8), tok(t, ".ashworth", {2: 0.6, O: 0.4})])
    assert [t[s.start:s.end] for s in decode(t, r)] == ["zbrennan", "bill.ashworth"]


def test_id_types_without_two_digits_are_dropped():
    """The vendor's format check: a username tagged ACCOUNT_IDENTIFIER without digits does not survive."""
    t = 'user = "zbrennan", "jdoe42"'
    r = raw([tok(t, "zbrennan", {0: 0.9, O: 0.1}, b=0.9), tok(t, "jdoe42", {0: 0.9, O: 0.1}, b=0.9)])
    assert [t[s.start:s.end] for s in decode(t, r)] == ["jdoe42"]


def test_format_checks():
    t = "tel 1234 or 0470 123 456, id A1"
    r = raw([tok(t, "1234", {3: 1.0}, b=1.0), tok(t, "0470", {3: 1.0}, b=1.0), tok(t, "123", {3: 1.0}, start=12),
             tok(t, "456", {3: 1.0}), tok(t, "A1", {0: 1.0}, b=1.0)])
    assert [t[s.start:s.end] for s in decode(t, r)] == ["0470 123 456"]  # phone needs 5+ digits, IDs 2+


def test_regex_email_replaces_overlapping_spans():
    t = "mail jan.peeters@example.be today"
    r = raw([tok(t, "jan", {2: 0.9, O: 0.1}, b=1.0), tok(t, ".peeters@example.be", {2: 0.9, O: 0.1})])
    assert decode(t, r) == [Span(5, 27, "EMAIL_ADDRESS")]


def test_overlapping_windows_are_averaged_per_character():
    t = "Jan here"
    a = [tok(t, "Jan", {2: 0.9, O: 0.1}, b=1.0)]
    b = [tok(t, "Jan", {2: 0.05, O: 0.95}, b=1.0)]
    assert decode(t, raw(a, b)) == []  # means: PERSON_NAME 0.475, O 0.525
    assert decode(t, raw(a, a))[0].type == "PERSON_NAME"


def test_threshold_drops_weak_model_spans_but_not_emails():
    t = "Jan x@y.be"
    r = raw([tok(t, "Jan", {2: 0.6, O: 0.4}, b=1.0)])
    assert [s.type for s in decode(t, r, threshold=0.7)] == ["EMAIL_ADDRESS"]
