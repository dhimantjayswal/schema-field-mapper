"""Fakes that keep the test suite cold — no network, no API key, no model
download. Used to exercise the real pipeline wiring (Stages 0-7) with
deterministic, inspectable substitutes for the embedder and the LLM.
"""
import re

import numpy as np

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD = re.compile(r"[^a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    text = _CAMEL_BOUNDARY.sub(" ", text)
    text = _NON_WORD.sub(" ", text)
    return [t for t in text.lower().split() if t]


class FakeEmbedder:
    """Deterministic bag-of-words embedder — no model download needed.
    Tokenizes on non-word characters and camelCase boundaries so dotted
    'table.field' descriptions and camelCase Mongo field names overlap the
    way a real embedding model's semantics would.
    """

    def encode(self, texts: list[str]) -> np.ndarray:
        vocab: dict[str, int] = {}
        tokenized = [_tokenize(text) for text in texts]
        for words in tokenized:
            for word in words:
                vocab.setdefault(word, len(vocab))

        rows = []
        for words in tokenized:
            vec = np.zeros(max(len(vocab), 1))
            for word in words:
                vec[vocab[word]] += 1.0
            rows.append(vec)
        return np.array(rows)


class FakeLLMClient:
    """Parses the candidate list back out of the prompt text and picks the
    top-ranked candidate for each field — enough to exercise the full
    pipeline (Stage 4 and Stage 7) without any real LLM call.
    """

    def map_fields(self, prompt: str) -> dict:
        field_mappings = []
        unmapped = []
        for line in prompt.splitlines():
            if not line.startswith("- ") or " -> candidates:" not in line:
                continue
            field, rest = line[2:].split(" -> candidates:", 1)
            field = field.strip()
            candidates = rest.strip(" []")
            first = candidates.split(",")[0].strip() if candidates else ""
            if not first:
                unmapped.append(field)
                continue
            dest_field = first.split(" (")[0]
            field_mappings.append({
                "source_field": field,
                "destination_field": dest_field,
                "type_transform": "auto (fake test client)",
                "confidence": 0.9,
                "reasoning": "Top embedding candidate selected by the fake test client.",
                "notes": None,
            })
        return {"field_mappings": field_mappings, "unmapped_source_fields": unmapped}
