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
    """Anything with `.map_fields(prompt) -> dict` matching `_FIELD_MAPPING_SCHEMA`.

    Satisfied by `ClaudeLLMClient`, `OllamaLLMClient`, and (for cold tests)
    `tests.fakes.FakeLLMClient` — `pipeline.map_fields.map_table` and
    `pipeline.reask.reask_low_confidence` are written against this
    interface, not any specific provider.
    """

    def map_fields(self, prompt: str) -> dict:
        """Send `prompt` to the LLM and return its structured response.

        Args:
            prompt: Built by `pipeline.prompts.build_field_mapping_prompt`
                or `build_reask_prompt`.

        Returns:
            A dict matching `_FIELD_MAPPING_SCHEMA`:
            `{"field_mappings": [...], "unmapped_source_fields": [...]}`.
        """
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
    """Real client — forces structured JSON output via tool use.

    The primary design target for this pipeline (see WRITEUP.md). Claude
    is given exactly one tool (`emit_field_mappings`) and `tool_choice`
    forces it to be called, so the response is always a validated
    `_FIELD_MAPPING_SCHEMA`-shaped dict — no free-text parsing needed.

    Example:
        $ export ANTHROPIC_API_KEY=sk-ant-...
        >>> client = ClaudeLLMClient()  # doctest: +SKIP
        >>> client.map_fields("SOURCE TABLE: locations\\n...")  # doctest: +SKIP
        {'field_mappings': [...], 'unmapped_source_fields': [...]}
    """

    _MODEL = "claude-sonnet-4-5"
    _TOOL_NAME = "emit_field_mappings"
    _TOOL_SCHEMA = {
        "name": _TOOL_NAME,
        "description": "Return the field mappings for this source table.",
        "input_schema": _FIELD_MAPPING_SCHEMA,
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Args:
            api_key: Defaults to the `ANTHROPIC_API_KEY` environment
                variable (loaded from `.env` by `run_pipeline.py` via
                `python-dotenv`). Raises immediately if neither is set —
                fail at construction, not on the first real call.
        """
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — export it, put it in .env, "
                "or pass api_key= explicitly."
            )
        self._client = None

    def _anthropic(self):
        """Lazily construct the `anthropic.Anthropic` client (avoids the
        import — and any credential check the SDK does — until the first
        real call)."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def map_fields(self, prompt: str) -> dict:
        """See `LLMClient.map_fields`. Raises `RuntimeError` if Claude
        responds without calling the forced tool (shouldn't happen given
        `tool_choice`, but fails loudly instead of silently returning
        `None` if it ever does)."""
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
    gets the same guarantee `ClaudeLLMClient` gets from tool-use: a
    response that's always valid against `_FIELD_MAPPING_SCHEMA`. Used
    automatically by `run_pipeline.py` when `ANTHROPIC_API_KEY` isn't set.

    Example:
        $ ollama pull qwen2.5:7b   # once
        $ ollama serve             # if not already running
        >>> client = OllamaLLMClient(model="qwen2.5:7b")
        >>> client.map_fields("SOURCE TABLE: locations\\n...")  # doctest: +SKIP
        {'field_mappings': [...], 'unmapped_source_fields': [...]}
    """

    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434") -> None:
        """
        Args:
            model: Any Ollama model tag already pulled locally (`ollama list`
                to check, `ollama pull <tag>` if not). `qwen2.5:7b` is a
                reasonable default — small enough to run on a laptop CPU,
                good enough at structured JSON to be usable here.
            host: Ollama's local API address — the default matches
                `ollama serve`'s default; only override for a remote or
                non-default Ollama instance.
        """
        self._model = model
        self._host = host.rstrip("/")

    def map_fields(self, prompt: str) -> dict:
        """See `LLMClient.map_fields`.

        Raises:
            RuntimeError: If the local Ollama server can't be reached —
                the message tells you exactly what to check (`ollama
                serve` running, model pulled) rather than leaking a raw
                `URLError`.
        """
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
