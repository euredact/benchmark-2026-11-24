"""OpenAI Privacy Filter (`openai/privacy-filter`), run with OpenAI's reference package `opf`: Viterbi span decoding
at the checkpoint's default operating point, as the model card describes it. Two ways to run it, same output:

- `base_url` in the config, or the environment variable OPF_BASE_URL: an `opf` service (bench/opf_server.py) on another
  machine, e.g. a rented GPU box through a tunnel (the same config either way, so runs are named and scored alike);
- otherwise locally: `opf` loaded here, on `device` (cpu by default). This is how the public kit runs it.

Config: `model_path` (the checkpoint's `original/` folder; may use ${BENCH_DATA_DIR}), `model_revision` (the Hugging
Face revision it was downloaded at, recorded), `device`, `base_url`, `timeout_s`. The model reads the whole document
(128k-token context): no windows. Every span is checked against the text it claims to cover.
"""

from __future__ import annotations

import importlib.metadata
import os
import threading
from pathlib import Path

from bench.adapters.base import Adapter, Parsed, Span
from bench.adapters.http import request_json
from bench.data import _expand


class OpenAIPrivacyFilterAdapter(Adapter):
    name = "openai_pf"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self._model = None
        self._lock = threading.RLock()  # call() holds it while _local() loads the model

    def _local(self):
        with self._lock:
            if self._model is None:
                from opf import OPF

                self._model = OPF(model=_expand(self.config["model_path"]), device=self.config.get("device", "cpu"))
            return self._model

    def _base(self) -> str | None:
        url = self.config.get("base_url") or os.environ.get("OPF_BASE_URL")
        return url.rstrip("/") if url else None

    def preflight(self) -> None:
        if self._base():
            request_json("GET", self._base() + "/health", {}, timeout=30)
        elif not (Path(_expand(self.config["model_path"])) / "model.safetensors").is_file():
            raise FileNotFoundError(f"no checkpoint at {self.config['model_path']}")

    def versions(self) -> dict[str, str]:
        out = {"model_revision": str(self.config.get("model_revision", "")), "mode": "remote" if self._base() else "local"}
        if self._base():
            health = request_json("GET", self._base() + "/health", {}, timeout=30)
            out.update({f"server.{k}": str(v) for k, v in health.items() if k != "status"})
        else:
            out.update({"opf": importlib.metadata.version("opf"), "device": self.config.get("device", "cpu")})
            try:
                import torch
                out["torch"] = torch.__version__
            except Exception:  # noqa: BLE001
                pass
        return out

    def call(self, text, lang):
        if self._base():
            raw = request_json("POST", self._base() + "/redact", {}, {"text": text},
                               timeout=self.config.get("timeout_s", 600))
        else:
            with self._lock:  # one forward pass at a time on one model
                r = self._local().redact(text)
            raw = {"spans": [{"label": s.label, "start": s.start, "end": s.end, "text": s.text}
                             for s in r.detected_spans], "warning": r.warning}
        return raw, {"requests": 1, "characters": len(text)}, str(self.config.get("model_revision", ""))

    def parse(self, raw, text, lang):
        spans, bad = [], []
        for s in raw["spans"]:
            if text[s["start"]:s["end"]] != s["text"]:
                bad.append({"text": s["text"], "type": s["label"]})
                continue
            spans.append(Span(s["start"], s["end"], s["label"]))
        spans.sort(key=lambda x: (x.start, x.end, x.type))
        return Parsed(spans, len(bad), bad)
