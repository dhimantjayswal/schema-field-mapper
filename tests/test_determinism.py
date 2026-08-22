"""Determinism regression test.

A live run without temperature=0 produced two different mappings from two
otherwise-identical invocations (see WRITEUP.md) — a real problem for an
artifact meant to be diffable and reviewable. This test can't exercise the
temperature setting itself (that's live-LLM territory, see
06-TESTING-style reasoning in WRITEUP.md about not asserting on live model
output in a test suite), but it does lock in the part this codebase fully
controls: given the same LLM/embedder responses, the pipeline's own logic
introduces no hidden randomness (dict-ordering, id()-based tie-breaks,
uuid4, time.time(), etc.) into the output.
"""
from pipeline.align_tables import align_tables
from pipeline.assemble import assemble
from pipeline.map_fields import map_table
from pipeline.reask import reask_low_confidence
from pipeline.validate import validate_table_mapping
from tests.fakes import FakeEmbedder, FakeLLMClient


def _run():
    """One full cold pipeline run (Stages 1, 3-7) with fixed `generated_at`,
    so two calls are comparable for exact equality."""
    embedder, llm = FakeEmbedder(), FakeLLMClient()
    tables = []
    for alignment in align_tables():
        raw = map_table(alignment["source_table"], alignment["destination_collection"], llm, embedder)
        table = validate_table_mapping(raw, alignment["confidence"], alignment["reasoning"])
        tables.append(reask_low_confidence(table, llm))
    return assemble(tables, generated_at="2026-01-01T00:00:00+00:00")


def test_two_runs_produce_identical_output():
    """Two cold runs over the same fake responses produce byte-identical output."""
    assert _run() == _run()
