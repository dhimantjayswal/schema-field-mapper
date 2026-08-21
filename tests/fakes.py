"""Fakes that keep the test suite cold — no network, no API key, no model
download. Used to exercise the real pipeline wiring (Stages 0-7) with
deterministic, inspectable substitutes for the embedder and the LLM.
"""
import numpy as np

from pipeline.names import tokenize


class FakeEmbedder:
    """Deterministic bag-of-words embedder — no model download needed.

    Satisfies `pipeline.embed_candidates.Embedder`. Uses the same
    `pipeline.names.tokenize` the real name-overlap boost uses, so dotted
    'table.field' descriptions and camelCase Mongo field names overlap
    roughly the way a real embedding model's semantics would.

    Example:
        >>> vecs = FakeEmbedder().encode(["is_remote", "isRemote", "unrelated"])
        >>> vecs.shape
        (3, 3)
        >>> bool((vecs[0] == vecs[1]).all())  # "is_remote" and "isRemote" tokenize identically
        True
    """

    def encode(self, texts: list[str]) -> np.ndarray:
        vocab: dict[str, int] = {}
        tokenized = [tokenize(text) for text in texts]
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
    """Satisfies `pipeline.llm_client.LLMClient` without a real LLM call.

    Parses the candidate list back out of the prompt text built by
    `pipeline.prompts.build_field_mapping_prompt` and picks the top-ranked
    candidate for each field — enough to exercise the full pipeline
    (Stage 4 and Stage 7) end to end with fixed, inspectable logic.

    Example:
        >>> prompt = (
        ...     "SOURCE TABLE: emp_master\\n"
        ...     "- is_remote -> candidates: [employment.isRemote (Boolean), _id (ObjectId)]\\n"
        ...     "- work_phone -> candidates: []\\n"
        ... )
        >>> result = FakeLLMClient().map_fields(prompt)
        >>> result["field_mappings"][0]["destination_field"]
        'employment.isRemote'
        >>> result["unmapped_source_fields"]
        ['work_phone']
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
