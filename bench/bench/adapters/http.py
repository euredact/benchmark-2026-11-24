"""Minimal JSON over HTTPS for the cloud adapters (stdlib only). Errors raise, so the run's retry/backoff applies."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class HTTPStatusError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def request_json(method: str, url: str, headers: dict[str, str], body: dict | None = None, timeout: float = 120.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise HTTPStatusError(e.code, e.read().decode("utf-8", "replace")) from None


def env(name: str) -> str:
    """A credential or endpoint from the environment; never logged."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise KeyError(f"environment variable {name} is not set")
    return value
