"""Mistral chat completions (Mistral Small 4, Mistral Large 4) with structured output. Key: MISTRAL_API_KEY."""

from __future__ import annotations

from bench.adapters.http import env, request_json
from bench.adapters.llm import OUTPUT_SCHEMA, LLMAdapter

URL = "https://api.mistral.ai/v1/chat/completions"


class MistralAdapter(LLMAdapter):
    name = "mistral"

    def preflight(self) -> None:
        env("MISTRAL_API_KEY")

    def complete(self, system, user):
        body = {
            "model": self.config["model"],
            "temperature": self.config.get("temperature", 0.0),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "pii_entities", "schema": OUTPUT_SCHEMA, "strict": True}},
        }
        if "top_p" in self.config:  # Mistral Large 4 refuses greedy sampling (temperature 0) unless top_p is 1
            body["top_p"] = self.config["top_p"]
        if self.config.get("reasoning_effort"):
            body["reasoning_effort"] = self.config["reasoning_effort"]
        raw = request_json("POST", URL, {"Authorization": f"Bearer {env('MISTRAL_API_KEY')}"}, body,
                           timeout=self.config.get("timeout_s", 300))
        usage = raw.get("usage") or {}
        billed = {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)}
        return raw, self.content(raw), billed, raw.get("model")

    def content(self, raw):
        content = raw["choices"][0]["message"]["content"]
        if isinstance(content, list):  # reasoning models (Mistral Large 4): [{"type": "thinking", ...}, {"type": "text", ...}]
            return "".join(c.get("text", "") for c in content if c.get("type") == "text")
        return content
