"""Stage 3 (embedding-based candidate retrieval) regression tests.

Uses `tests.fakes.FakeEmbedder` (deterministic bag-of-words, no model
download) so these stay cold. Covers the `k` cap and the specific
`is_remote` -> `employment.isRemote` case the name-overlap blend in
`pipeline.embed_candidates._name_overlap` exists to fix — see that
module's docstring for the real miss this guards against.
"""
from pipeline.embed_candidates import top_k_candidates
from pipeline.parse_schema import fields_for_collection, fields_for_table
from tests.fakes import FakeEmbedder


def test_top_k_returns_at_most_k_candidates_per_field():
    """Every source field gets a candidate list capped at `k`, one entry per field."""
    source_fields = fields_for_table("emp_master")
    dest_fields = fields_for_collection("employees")

    results = top_k_candidates(source_fields, dest_fields, FakeEmbedder(), k=3)

    assert set(results.keys()) == {f.field for f in source_fields}
    for candidates in results.values():
        assert len(candidates) <= 3


def test_is_remote_prefers_isremote_over_unrelated_fields():
    """`is_remote`'s candidates include `employment.isRemote` — the real
    near-miss the name-overlap blend exists to rescue."""
    source_fields = [f for f in fields_for_table("emp_master") if f.field == "is_remote"]
    dest_fields = fields_for_collection("employees")

    results = top_k_candidates(source_fields, dest_fields, FakeEmbedder(), k=5)
    top_paths = [d.path for d, _score in results["is_remote"]]

    assert "employment.isRemote" in top_paths
