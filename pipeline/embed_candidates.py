"""Stage 3 — embedding-based candidate retrieval (RAG).

Embeds destination fields (scoped to the collection Stage 1 already matched)
and source fields, then returns each source field's top-k destination
candidates by cosine similarity. This is what keeps Stage 4 from ever
needing to see the full destination schema — it only sees a short,
pre-filtered candidate list per field.

Embedder is a plain Protocol so tests can inject a fake, network-free
implementation instead of downloading the real sentence-transformers model.

Retrieval blends cosine similarity with a literal name-overlap score. A
real run against MiniLM found `is_remote` -> `employment.isRemote` — a
near-exact name match — ranked 18th of 25 (score 0.058) on embedding
similarity alone, because the short `description` string ("TINYINT(1) —
0 or 1") gives the type/comment noise as much weight as the field name
itself. The name-overlap term fixes exactly that failure mode without
touching the genuinely semantic matches embeddings already get right.
"""
from typing import Protocol

import numpy as np

from pipeline.lexicon import expand
from pipeline.names import tokenize
from pipeline.parse_schema import DestField, SourceField


def _name_overlap(source_field: str, dest_path: str) -> float:
    """Jaccard similarity between a source field name and a destination
    path's last segment, tokenized with `pipeline.names.tokenize` and
    expanded with `pipeline.lexicon.expand`.

    This is what rescues near-exact name matches (e.g. `is_remote` vs.
    `isRemote`) that a generic sentence embedding can under-rank when the
    field's type/comment text dominates the embedded string — see this
    module's docstring for the real case that motivated it. Lexicon
    expansion extends this to abbreviated matches embeddings alone also
    miss: `tz_cd` shares no literal tokens with `timezone`, but both
    expand to `{"timezone"}`.

    Args:
        source_field: A source column name, e.g. "is_remote".
        dest_path: A destination dot-path — only its last segment is
            compared, e.g. "employment.isRemote" -> "isRemote".

    Returns:
        0.0 to 1.0 — 1.0 means identical expanded token sets, 0.0 means no
        shared tokens (or either name tokenizes to nothing).

    Example:
        >>> _name_overlap("is_remote", "employment.isRemote")
        1.0
        >>> round(_name_overlap("tz_cd", "timezone"), 3)
        0.5
        >>> _name_overlap("dept_stat", "isActive")
        0.0
    """
    a = set(expand(tokenize(source_field)))
    b = set(expand(tokenize(dest_path.rsplit(".", 1)[-1])))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Embedder(Protocol):
    """Anything with `.encode(texts) -> array of shape (len(texts), dim)`.

    Satisfied by `sentence_transformers.SentenceTransformer` directly, so
    `SentenceTransformerEmbedder` below is mostly a lazy-import wrapper.
    Tests satisfy it with `tests.fakes.FakeEmbedder` instead, so the cold
    suite never downloads a model.
    """

    def encode(self, texts: list[str]) -> np.ndarray:
        """Embed `texts` into a `(len(texts), dim)` float array, one row
        per input string, in the same order."""
        ...


class SentenceTransformerEmbedder:
    """Local, offline embedder — default for real runs. No API key needed.

    The model (`all-MiniLM-L6-v2`, ~90MB) downloads once on first
    `.encode()` call and is cached by `sentence-transformers`; construction
    itself does no I/O, so this is cheap to instantiate even if you end up
    using `OllamaLLMClient`/`ClaudeLLMClient` interchangeably elsewhere.

    Example:
        >>> embedder = SentenceTransformerEmbedder()  # no download yet
        >>> vectors = embedder.encode(["is_remote", "isRemote"])  # doctest: +SKIP
        >>> vectors.shape  # doctest: +SKIP
        (2, 384)
    """

    _MODEL_NAME = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        """No I/O here — the model downloads/loads lazily on first `.encode()`."""
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        """See `Embedder.encode`. Downloads/loads `_MODEL_NAME` on the
        first call, then reuses the cached instance for every call after."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._MODEL_NAME)
        return np.asarray(self._model.encode(texts))


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between two embedding matrices.

    Args:
        a: Shape `(n, dim)`.
        b: Shape `(m, dim)`.

    Returns:
        Shape `(n, m)`; entry `[i, j]` is the cosine similarity between
        `a[i]` and `b[j]`.

    Example:
        >>> import numpy as np
        >>> a = np.array([[1.0, 0.0], [0.0, 1.0]])
        >>> b = np.array([[1.0, 0.0], [1.0, 1.0]])
        >>> np.round(_cosine_sim(a, b), 3)
        array([[1.   , 0.707],
               [0.   , 0.707]])
    """
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
    name_weight: float = 0.3,
) -> dict[str, list[tuple[DestField, float]]]:
    """Stage 3: retrieve each source field's top-k destination candidates.

    Scores every (source field, destination field) pair by blending
    embedding cosine similarity with `_name_overlap`, then keeps the
    top `k` per source field. This is the mechanism that satisfies the
    assignment's core constraint — Stage 4's LLM call never sees the full
    destination schema, only this short, pre-filtered candidate list.

    Args:
        source_fields: Fields of one source table (e.g.
            `fields_for_table("emp_master")`) — typically not the whole
            source schema, since candidates should be scoped per table.
        dest_fields: Fields of the destination collection Stage 1 already
            matched to that table (e.g. `fields_for_collection("employees")`).
        embedder: Anything satisfying `Embedder` — `SentenceTransformerEmbedder`
            for real runs, `tests.fakes.FakeEmbedder` for cold tests.
        k: Candidates to keep per source field.
        name_weight: Blend weight for `_name_overlap`, 0-1. `0` uses pure
            embedding similarity; `1` uses pure name overlap. `0.3` was
            tuned to fix a real miss — see the module docstring.

    Returns:
        `{source_field_name: [(DestField, blended_score), ...]}`, one
        entry per input source field, candidates sorted best-first.

    Example:
        >>> from pipeline.parse_schema import fields_for_table, fields_for_collection
        >>> from tests.fakes import FakeEmbedder
        >>> src = [f for f in fields_for_table("emp_master") if f.field == "is_remote"]
        >>> dst = fields_for_collection("employees")
        >>> result = top_k_candidates(src, dst, FakeEmbedder(), k=1)
        >>> result["is_remote"][0][0].path
        'employment.isRemote'
    """
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
        scored = [
            (d, (1 - name_weight) * float(sims[i][j]) + name_weight * _name_overlap(sfield.field, d.path))
            for j, d in enumerate(dest_fields)
        ]
        ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)[:k]
        results[sfield.field] = ranked
    return results
