"""bards.ai eu-pii-anonimization-multilang (v2, v3), local, decoded the way the model card's bundled `pii_detector.py`
does it (identical in v2 and v3; Apache-2.0). Ported here, not imported, so the decoding runs from raw/:

  1. Windows of `max_input_tokens` (512, the card's max_len) from chunk.split, overlapping `overlap_tokens` (128, its
     stride). Per token: softmax, pooled per entity type (B- + I- mass) plus O, and the B- mass.
  2. Per character (a token's first non-space character): pooled probabilities, token count and B mass, summed over
     all windows, so overlapping windows are averaged before decoding (as the card's code does).
  3. Words: runs of characters other than whitespace and , ; | " < > ( ) [ ] { } * ^, with edge punctuation trimmed.
     A word's label is the argmax of its mean pooled probabilities; O means no span.
  4. Adjacent words of the same type merge when only " ,-/.()" lies between them, no blank line, and the next word's
     B mass is below 0.5.
  5. Format checks: IDENTIFYING_LINK must look like a URL, PHONE_NUMBER needs 5+ digits, ID types 2+ digits.
  6. Every regex-matched email address is EMAIL_ADDRESS, replacing overlapping spans.

The only deviation: windows break at paragraph/sentence boundaries (the shared splitter) rather than wherever the
tokenizer's overflow cuts. raw/ keeps, per window, each token's character and its pooled probabilities (>= 1e-5,
5 decimals) and B mass. `threshold` drops model spans whose mean word probability is lower (default 0: the card's
plain argmax); regex emails always stay.

Config: `model`, `revision` (pinned), `max_input_tokens`, `overlap_tokens`, `threshold`.
"""

from __future__ import annotations

import importlib.metadata
import re

from bench.adapters.base import Adapter, Parsed, Span
from bench.chunk import split

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}(?![\w-])")
_URLISH = re.compile(r"(https?://|www\.|\w\.[a-z]{2,}\b|/\w)", re.I)
_WORD = re.compile(r"[^\s,;|\"<>()\[\]{}*^]+")
_ID_TYPES = ("PERSON_IDENTIFIER", "BANK_ACCOUNT_IDENTIFIER", "PAYMENT_CARD", "ACCOUNT_IDENTIFIER",
             "DOCUMENT_IDENTIFIER", "VEHICLE_IDENTIFIER")
_MIN_P = 1e-5


def valid(text: str, s: int, e: int, t: str) -> bool:
    v = text[s:e]
    digits = sum(c.isdigit() for c in v)
    if t == "IDENTIFYING_LINK":
        return bool(_URLISH.search(v))
    if t == "PHONE_NUMBER":
        return digits >= 5
    if t in _ID_TYPES:
        return digits >= 2
    return True


class BardsAdapter(Adapter):
    name = "bards"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self.max_input_tokens = config.get("max_input_tokens", 512)
        self._tok = self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer

            kw = {"revision": self.config["revision"]}
            self._tok = AutoTokenizer.from_pretrained(self.config["model"], **kw)
            self._model = AutoModelForTokenClassification.from_pretrained(self.config["model"], **kw).eval()
            id2label = {int(k): v for k, v in self._model.config.id2label.items()}
            self._types = sorted({lab.split("-", 1)[1] for lab in id2label.values() if lab != "O"})
            tix = {t: i for i, t in enumerate(self._types)}
            n = len(id2label)
            self._pool = torch.zeros(n, len(self._types) + 1)  # label -> type, last column O
            for i, lab in id2label.items():
                self._pool[i, len(self._types) if lab == "O" else tix[lab.split("-", 1)[1]]] = 1
            self._is_b = torch.tensor([1.0 if id2label[i].startswith(("B-", "S-")) else 0.0 for i in range(n)])
        return self._tok, self._model

    def versions(self) -> dict[str, str]:
        out = {p: importlib.metadata.version(p) for p in ("torch", "transformers")}
        out[self.config["model"]] = self.config["revision"]
        return out

    def _count(self, text: str) -> int:
        return len(self._tok(text)["input_ids"])  # special tokens included

    def call(self, text, lang):
        import torch

        tok, model = self._load()
        windows = split(text, self.max_input_tokens, self._count, self.config.get("overlap_tokens", 128))
        out = []
        for w in windows:
            enc = tok(text[w.start:w.end], return_offsets_mapping=True, return_tensors="pt")
            offsets = enc.pop("offset_mapping")[0].tolist()
            with torch.inference_mode():
                probs = model(**enc).logits[0].float().softmax(-1)
            pooled, bmass = (probs @ self._pool).tolist(), (probs @ self._is_b).tolist()
            tokens = []
            for (s, e), p, b in zip(offsets, pooled, bmass):
                if e <= s:
                    continue
                s += w.start
                while s < w.start + e - 1 and text[s].isspace():  # byte-BPE offsets include the leading space
                    s += 1
                tokens.append([s, {str(i): round(x, 5) for i, x in enumerate(p) if x >= _MIN_P}, round(b, 5)])
            out.append({"window": [w.start, w.end], "tokens": tokens})
        version = f"{self.config['model']}@{self.config['revision'][:12]}"
        return {"types": self._types, "windows": out}, {"windows": len(windows)}, version

    def parse(self, raw, text, lang):
        return Parsed(decode(text, raw, self.config.get("threshold", 0.0)))


def decode(text: str, raw: dict, threshold: float = 0.0) -> list[Span]:
    types = raw["types"]
    o_index = len(types)
    acc: dict[int, list[float]] = {}
    cnt: dict[int, int] = {}
    bmass: dict[int, float] = {}
    for win in raw["windows"]:
        for c, probs, b in win["tokens"]:
            vec = acc.setdefault(c, [0.0] * (o_index + 1))
            for i, p in probs.items():
                vec[int(i)] += p
            cnt[c] = cnt.get(c, 0) + 1
            bmass[c] = bmass.get(c, 0.0) + b

    spans: list[list] = []  # [start, end, type, [word scores]]
    for m in _WORD.finditer(text):
        ws, we = m.start(), m.end()
        while ws < we and text[ws] in "([{<\"'«„":
            ws += 1
        while we > ws and text[we - 1] in ")]}>\"'».,;:!?":
            we -= 1
        chars = [c for c in range(ws, we) if c in cnt]
        if not chars:
            continue
        total = sum(cnt[c] for c in chars)
        mean = [sum(acc[c][k] for c in chars) / total for k in range(o_index + 1)]
        k = max(range(o_index + 1), key=mean.__getitem__)
        if k == o_index:
            continue
        t = types[k]
        start_b = bmass[chars[0]] / cnt[chars[0]]
        if (spans and spans[-1][2] == t and text[spans[-1][1]:ws].strip(" ,-/.()") == ""
                and "\n\n" not in text[spans[-1][1]:ws] and start_b < 0.5):
            spans[-1][1] = we
            spans[-1][3].append(mean[k])
        else:
            spans.append([ws, we, t, [mean[k]]])

    out = [Span(s, e, t, round(sum(sc) / len(sc), 6)) for s, e, t, sc in spans
           if valid(text, s, e, t) and sum(sc) / len(sc) >= threshold]
    emails = [(m.start(), m.end()) for m in _EMAIL.finditer(text)]
    if emails:
        out = [s for s in out if not any(s.start < b and a < s.end for a, b in emails)]
        out += [Span(a, b, "EMAIL_ADDRESS") for a, b in emails]
    return sorted(out, key=lambda s: (s.start, s.end, s.type))
