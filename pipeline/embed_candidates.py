"""Stage 3 — embedding-based candidate retrieval (RAG).

Embeds destination fields (scoped to the collection Stage 1 already matched)
and source fields, then returns each source field's top-k destination
candidates by cosine similarity. This is what keeps Stage 4 from ever
needing to see the full destination schema — it only sees a short,
pre-filtered candidate list per field.

Embedder is a plain Protocol so tests can inject a fake, network-free
implementation instead of downloading the real sentence-transformers model.
"""
from typing import Protocol

import numpy as np

from pipeline.parse_schema import DestField, SourceField


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:
        ...


class SentenceTransformerEmbedder:
    """Local, offline embedder — default for real runs. No API key needed."""

    _MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._MODEL_NAME)
        return np.asarray(self._model.encode(texts))


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-9, None)
    b_norm = b / np.clip(np.linalg.norm(b, axis=1, keepdims=True), 1e-9, None)
    # macOS/Apple Silicon numpy builds route matmul through the Accelerate
    # BLAS, which emits spurious divide-by-zero/invalid-value warnings on
    # perfectly valid float64 input (norms are already clipped above, so
    # there's nothing actually invalid here) — known numpy/Accelerate quirk.
    with np.errstate(all="ignore"):
        return a_norm @ b_norm.T


def top_k_candidates(
    source_fields: list[SourceField],
    dest_fields: list[DestField],
    embedder: Embedder,
    k: int = 5,
) -> dict[str, list[tuple[DestField, float]]]:
    if not source_fields or not dest_fields:
        return {f.field: [] for f in source_fields}

    # Encoded together in one call so both matrices share the same
    # dimensionality/vocabulary regardless of embedder implementation.
    n = len(source_fields)
    texts = [f.description for f in source_fields] + [f.description for f in dest_fields]
    vecs = embedder.encode(texts)
    source_vecs, dest_vecs = vecs[:n], vecs[n:]
    sims = _cosine_sim(source_vecs, dest_vecs)

    results = {}
    for i, sfield in enumerate(source_fields):
        ranked = sorted(zip(dest_fields, sims[i]), key=lambda pair: pair[1], reverse=True)[:k]
        results[sfield.field] = [(d, float(score)) for d, score in ranked]
    return results
