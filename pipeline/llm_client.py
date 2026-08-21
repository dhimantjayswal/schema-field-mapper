"""Claude client wrapper used by Stage 4 (field mapping) and Stage 7 (re-ask).

Kept behind a small Protocol so tests substitute a fake client — the
pipeline never needs network access or an API key to be exercised cold.
"""
import os
from typing import Optional, Protocol


class LLMClient(Protocol):
    def map_fields(self, prompt: str) -> dict:
        ...


class ClaudeLLMClient:
    """Real client — forces structured JSON output via tool use."""

    _MODEL = "claude-sonnet-4-5"
    _TOOL_NAME = "emit_field_mappings"
    _TOOL_SCHEMA = {
        "name": _TOOL_NAME,
        "description": "Return the field mappings for this source table.",
        "input_schema": {
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
        },
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
