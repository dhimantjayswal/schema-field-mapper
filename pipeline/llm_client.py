"""LLM client wrappers used by Stage 4 (field mapping) and Stage 7 (re-ask).

Kept behind a small Protocol so tests substitute a fake client — the
pipeline never needs network access or an API key to be exercised cold.

Two real implementations: Claude (paid API, the primary design target) and
Ollama (a local model, no API key or cost — see WRITEUP.md for why this
exists). Both are handed the same JSON schema so either produces identical
output shape.
"""
import json
import os
import urllib.request
from typing import Optional, Protocol


class LLMClient(Protocol):
    def map_fields(self, prompt: str) -> dict:
        ...


_FIELD_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "field_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_field": {"type": "string"},
                    "destination_field": {"type": "string"},
                    "type_transform": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                    "notes": {"type": ["string", "null"]},
                },
                "required": [
                    "source_field", "destination_field", "type_transform",
                    "confidence", "reasoning", "notes",
                ],
            },
        },
        "unmapped_source_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["field_mappings", "unmapped_source_fields"],
}


class ClaudeLLMClient:
    """Real client — forces structured JSON output via tool use."""

    _MODEL = "claude-sonnet-4-5"
    _TOOL_NAME = "emit_field_mappings"
    _TOOL_SCHEMA = {
        "name": _TOOL_NAME,
        "description": "Return the field mappings for this source table.",
        "input_schema": _FIELD_MAPPING_SCHEMA,
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — export it, put it in .env, "
                "or pass api_key= explicitly."
            )
        self._client = None

    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def map_fields(self, prompt: str) -> dict:
        response = self._anthropic().messages.create(
            model=self._MODEL,
            max_tokens=4096,
            tools=[self._TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": self._TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == self._TOOL_NAME:
                return block.input
        raise RuntimeError("Claude did not return the expected tool call.")


class OllamaLLMClient:
    """Local client — no API key, no cost, no network beyond localhost.

    Uses Ollama's structured-output support (the `format` field takes a
    JSON schema and Ollama constrains generation to match it), so this
    gets the same guarantee ClaudeLLMClient gets from tool-use: a response
    that's always valid against _FIELD_MAPPING_SCHEMA.
    """

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434") -> None:
        self._model = model
        self._host = host.rstrip("/")

    def map_fields(self, prompt: str) -> dict:
        payload = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "format": _FIELD_MAPPING_SCHEMA,
            "stream": False,
        }).encode()
        request = urllib.request.Request(
            f"{self._host}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read())
        except OSError as exc:
            raise RuntimeError(
                f"Couldn't reach Ollama at {self._host} — is `ollama serve` running "
                f"and is `{self._model}` pulled (`ollama pull {self._model}`)?"
            ) from exc
        return json.loads(body["message"]["content"])
