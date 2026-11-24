import json

from bench.leaks import leak_report

TEXT = "Call Jan Peeters at +32 470 12 34 56. Acme NV pays EUR 50."
#       0123456789012345678901234567890123456789012345678901234567


def _write(tmp_path, preds):
    def at(piece):
        s = TEXT.index(piece)
        return s, s + len(piece)
    ents = [{**dict(zip(("start", "end"), at(p))), "text": p, "fine": f, "coarse": c, "redact": r}
            for p, f, c, r in [("Jan Peeters", "PERSON", "NAME", True), ("+32 470 12 34 56", "PHONE", "CONTACT", True),
                               ("Acme NV", "ORGANISATION", "ORG", False)]]
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"id": "d1", "lang": "nl", "genre": "x", "hard": [], "text": TEXT,
                                "entities": ents}) + "\n", encoding="utf-8")
    pred = tmp_path / "pred.jsonl"
    pred.write_text(json.dumps({"id": "d1", "entities": [
        {**dict(zip(("start", "end"), at(p))), "type": t} for p, t in preds]}) + "\n", encoding="utf-8")
    labels = {"fine": {"PERSON": {"coarse": "NAME"}, "PHONE": {"coarse": "CONTACT"},
                       "ORGANISATION": {"coarse": "ORG"}},
              "tool_mappings": {"t": {"N": "NAME", "P": "CONTACT", "O": "ORG", "M": "FINANCIAL"}}}
    return gold, pred, labels


def test_complete_partial_masked_and_over_redaction(tmp_path):
    # "Jan" and "Peeters" separately mask the whole name; the phone (11 digits) is 9/11 covered,
    # so partly redacted; EUR 50 is over-redaction; the ORG prediction is not a redaction at all.
    gold, pred, labels = _write(tmp_path, [("Jan", "N"), ("Peeters", "N"), ("+32 470 12 34", "P"), ("Acme NV", "O"),
                                           ("EUR 50", "M")])
    r = leak_report(gold, pred, labels, "t")["groups"]["ALL"]
    assert (r["gold_spans"], r["masked"], r["partial_leak"], r["complete_leak"], r["uncovered"]) == (2, 1, 1, 0, 0)
    assert (r["pred_spans"], r["over_redactions"], r["over_redactions_touching_org"]) == (4, 1, 0)


def test_under_75_percent_covered_counts_as_leaked(tmp_path):
    # "+32 470" covers 5 of the phone's 11 digits (45%): leaked, though not uncovered
    gold, pred, labels = _write(tmp_path, [("Jan Peeters", "N"), ("+32 470", "P")])
    r = leak_report(gold, pred, labels, "t")["groups"]["ALL"]
    assert (r["masked"], r["partial_leak"], r["complete_leak"], r["uncovered"]) == (1, 0, 1, 0)


def test_nothing_predicted_is_two_complete_leaks(tmp_path):
    gold, pred, labels = _write(tmp_path, [])
    rep = leak_report(gold, pred, labels, "t")
    assert rep["groups"]["ALL"]["complete_leak"] == 2 and rep["groups"]["ALL"]["uncovered"] == 2
    assert rep["groups"]["ALL"]["leaked_char_rate"] == 1.0 and rep["partial_min_coverage"] == 0.75
    assert rep["docs"] == {"n": 1, "with_complete_leak": 1, "with_any_leak": 1, "with_over_redaction": 0}
    assert rep["fine"]["PHONE"]["complete_leak"] == 1


def test_prediction_touching_only_an_org_is_flagged(tmp_path):
    gold, pred, labels = _write(tmp_path, [("Acme NV", "N")])  # an ORG redacted as a name
    r = leak_report(gold, pred, labels, "t")["groups"]["ALL"]
    assert (r["over_redactions"], r["over_redactions_touching_org"]) == (1, 1)


def test_mask_characters_and_punctuation_cannot_leak(tmp_path):
    # An already masked IBAN "**** 5813" with only "5813" predicted is masked: the asterisks reveal nothing.
    text = "IBAN **** 5813, mail j.d@x.be"
    ents = [{"start": 5, "end": 14, "text": "**** 5813", "fine": "IBAN", "coarse": "FINANCIAL", "redact": True},
            {"start": 21, "end": 29, "text": "j.d@x.be", "fine": "EMAIL", "coarse": "CONTACT", "redact": True}]
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"id": "d1", "lang": "nl", "genre": "x", "hard": [], "text": text, "entities": ents}) + "\n",
                    encoding="utf-8")
    pred = tmp_path / "pred.jsonl"  # "5813" and the e-mail's letters, but not its "." and "@"
    pred.write_text(json.dumps({"id": "d1", "entities": [{"start": 10, "end": 14, "type": "M"}, {"start": 21, "end": 22, "type": "P"},
                                                           {"start": 23, "end": 24, "type": "P"}, {"start": 25, "end": 26, "type": "P"},
                                                           {"start": 27, "end": 29, "type": "P"}]}) + "\n", encoding="utf-8")
    labels = {"fine": {"IBAN": {"coarse": "FINANCIAL"}, "EMAIL": {"coarse": "CONTACT"}},
              "tool_mappings": {"t": {"M": "FINANCIAL", "P": "CONTACT"}}}
    r = leak_report(gold, pred, labels, "t")["groups"]["ALL"]
    assert (r["masked"], r["partial_leak"], r["complete_leak"]) == (2, 0, 0)


def test_span_ending_past_the_text_is_clamped(tmp_path):
    # GLiNER2 once returned an IBAN span ending one character after the document's end
    text = "IBAN BE68539007547034"
    gold = tmp_path / "gold.jsonl"
    gold.write_text(json.dumps({"id": "d1", "lang": "nl", "genre": "x", "hard": [], "text": text, "entities": [
        {"start": 5, "end": 21, "text": "BE68539007547034", "fine": "IBAN", "coarse": "FINANCIAL", "redact": True}]}) + "\n",
        encoding="utf-8")
    pred = tmp_path / "pred.jsonl"
    pred.write_text(json.dumps({"id": "d1", "entities": [{"start": 5, "end": 22, "type": "M"}]}) + "\n", encoding="utf-8")
    labels = {"fine": {"IBAN": {"coarse": "FINANCIAL"}}, "tool_mappings": {"t": {"M": "FINANCIAL"}}}
    r = leak_report(gold, pred, labels, "t")["groups"]["ALL"]
    assert (r["masked"], r["complete_leak"], r["over_redactions"]) == (1, 0, 0)
