"""euRedact in production: the public SDK (`euredact` on PyPI) in cloud mode, exactly as a customer calls it.

The SDK runs the rules engine locally, sends the rules-masked text to the cloud model, and returns both tiers' spans
in original offsets. It needs exactly one country per request: `countries_by_lang` maps the document language to one.
The choice does not change what the cloud model finds.
There is no client-side segmentation (the service rejects oversized input; that document is then failed).
Key: EUREDACT_API_KEY, read by the SDK's own `euredact.configure()` (called once, without arguments: the SDK only
falls back to the environment there). A non-production gateway is set with `base_url` (exported as
EUREDACT_BASE_URL before configure) and `health_url`, so the version record describes that gateway. An SDK other than
the pinned one is run with `sdk_path` (a folder holding the `euredact` package, e.g. an unreleased build from the SDK
repository): it is put first on the import path, the run refuses to start if `euredact` is loaded from anywhere else,
and the loaded file is recorded with the versions. Thread-safe for `bench run --workers`. Versions: the SDK's, plus what the service's GET /health reports.
"""

from __future__ import annotations

import os
import sys
import threading

from bench.adapters.base import Adapter, Parsed, Span
from bench.adapters.http import env, request_json


class EuRedactCloudAdapter(Adapter):
    name = "euredact_cloud"

    def __init__(self, config: dict, context: dict | None = None):
        super().__init__(config, context)
        self._configured = False
        self._lock = threading.Lock()

    def preflight(self) -> None:
        if self.config.get("mode", "cloud") == "cloud":  # rules mode is the free, local engine: no key, no network
            env("EUREDACT_API_KEY")
        sdk_path = self.config.get("sdk_path")
        if sdk_path and sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)
        import euredact  # fail now if the SDK is missing

        if sdk_path and not os.path.realpath(euredact.__file__).startswith(os.path.realpath(sdk_path) + os.sep):
            raise RuntimeError(f"euredact is loaded from {euredact.__file__}, not from sdk_path {sdk_path}")

    def versions(self) -> dict[str, str]:
        import euredact

        out = {"euredact-sdk": euredact.__version__}
        if self.config.get("sdk_path"):
            out["euredact-sdk.file"] = euredact.__file__
            out["euredact-sdk.source"] = str(self.config.get("sdk_source", ""))
        try:
            health = request_json("GET", self.config.get("health_url", "https://api.euredact.dev/health"), {}, timeout=30)
            out.update({f"service.{k}": str(v) for k, v in health.items()
                        if k in ("model", "output_format", "rules_engine", "gateway_sdk_version", "min_sdk_version")})
        except Exception as e:  # noqa: BLE001 - versions are reported, a failure to fetch them is recorded
            out["service.health_error"] = f"{type(e).__name__}: {e}"[:200]
        return out

    def call(self, text, lang):
        import euredact

        with self._lock:
            if not self._configured and self.config.get("mode", "cloud") == "cloud":
                if self.config.get("base_url"):  # a non-production gateway: the SDK reads it from the environment only
                    os.environ["EUREDACT_BASE_URL"] = self.config["base_url"]
                euredact.configure()  # takes EUREDACT_API_KEY (and EUREDACT_BASE_URL) from the environment
                self._configured = True
        country = self.config["countries_by_lang"][lang]
        if self.config.get("mode", "cloud") == "rules":
            result = euredact.redact(text, countries=[country], mode="rules")
            raw = {"country": country, "source": result.source, "degraded": result.degraded, "mode": "rules",
                   "detections": [{"start": d.start, "end": d.end, "type": getattr(d.entity_type, "value", d.entity_type),
                                   "text": d.text, "source": getattr(d.source, "value", d.source),
                                   "confidence": d.confidence} for d in result.detections],
                   "cloud": {"unlocated": []}, "sdk_version": euredact.__version__}
            return raw, {"requests": 1, "characters": len(text)}, f"rules-{euredact.__version__}"
        result = euredact.redact(text, countries=[country], mode="cloud")
        cloud = result.cloud
        if result.source != "cloud" or result.degraded or cloud is None or not cloud.model_version:
            raise RuntimeError(f"not a cloud answer (source={result.source}, degraded={result.degraded})")
        raw = {
            "country": country,
            "source": result.source,
            "degraded": result.degraded,
            "detections": [{"start": d.start, "end": d.end, "type": getattr(d.entity_type, "value", d.entity_type),
                            "text": d.text, "source": getattr(d.source, "value", d.source),
                            "confidence": d.confidence} for d in result.detections],
            "cloud": {"job_id": cloud.job_id, "model_version": cloud.model_version,
                      "usage": _plain(cloud.usage), "unlocated": [_plain(u) for u in cloud.unlocated]},
            "sdk_version": euredact.__version__,
        }
        billed = {"requests": 1, "characters": len(text)}
        for k in ("tokens", "credits"):  # quantities only (billing_rate is a rate, not summed)
            v = (raw["cloud"]["usage"] or {}).get(k)
            if isinstance(v, (int, float)):
                billed[f"usage.{k}"] = v
        return raw, billed, cloud.model_version

    def parse(self, raw, text, lang):
        # The SDK's confidence is a label ("high") or None, not a number: no scores, and no merging needed.
        return Parsed([Span(d["start"], d["end"], d["type"]) for d in raw["detections"]],
                      unresolved=len(raw["cloud"]["unlocated"]), unresolved_quotes=raw["cloud"]["unlocated"])


def _plain(obj):
    import dataclasses

    if obj is None:
        return None
    if dataclasses.is_dataclass(obj):
        return {k: _plain(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return getattr(obj, "value", obj)
