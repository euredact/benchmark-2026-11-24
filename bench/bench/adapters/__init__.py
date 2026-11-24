"""Adapter registry: systems.yaml `adapter:` value -> class. Add one line per new adapter module."""

from __future__ import annotations

import importlib

from bench.adapters.base import Adapter, AdapterResult, Parsed, Span

_REGISTRY = {
    "gold": "bench.adapters.gold:GoldAdapter",
    "presidio": "bench.adapters.presidio:PresidioAdapter",
    "bards": "bench.adapters.bards:BardsAdapter",
    "gliner2": "bench.adapters.gliner2:GLiNER2Adapter",
    "mistral": "bench.adapters.mistral:MistralAdapter",
    "euredact_cloud": "bench.adapters.euredact_cloud:EuRedactCloudAdapter",
    "euredact_ts": "bench.adapters.euredact_ts:EuRedactTsAdapter",
    "openai_pf": "bench.adapters.openai_pf:OpenAIPrivacyFilterAdapter",
}


def get_adapter_class(name: str) -> type[Adapter]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown adapter {name!r}; known: {', '.join(sorted(_REGISTRY))}")
    module, cls = _REGISTRY[name].split(":")
    return getattr(importlib.import_module(module), cls)


__all__ = ["Adapter", "AdapterResult", "Parsed", "Span", "get_adapter_class"]
