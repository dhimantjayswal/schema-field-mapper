"""Cold end-to-end test: Stages 0-7 wired together with fakes standing in
for the embedder and the LLM. No network call, no ANTHROPIC_API_KEY, no
model download — this is what "cold test validations" means for this repo.
"""
from pipeline.align_tables import align_tables
from pipeline.assemble import assemble
from pipeline.map_fields import map_table
from pipeline.parse_schema import fields_for_table
from pipeline.reask import reask_low_confidence
from pipeline.validate import validate_table_mapping
from tests.fakes import FakeEmbedder, FakeLLMClient


def _run_cold_pipeline():
    """Stages 1, 3-7 wired together with fakes; returns the per-table
    `TableMapping` list `pipeline.assemble.assemble` would receive next."""
    embedder = FakeEmbedder()
    llm = FakeLLMClient()

    tables = []
    for alignment in align_tables():
        raw = map_table(
            alignment["source_table"], alignment["destination_collection"], llm, embedder,
        )
        table = validate_table_mapping(raw, alignment["confidence"], alignment["reasoning"])
        table = reask_low_confidence(table, llm, threshold=0.7)
        tables.append(table)
    return tables


def test_pipeline_runs_cold_end_to_end():
    """A cold run (Stages 1, 3-7 with fakes) produces one `TableMapping` per source table."""
    tables = _run_cold_pipeline()
    assert {t.source_table for t in tables} == {"emp_master", "dept_info", "locations"}


def test_every_source_field_accounted_for():
    """Every source field ends up either mapped or in `unmapped_source_fields` — never dropped."""
    tables = _run_cold_pipeline()
    for table in tables:
        expected = {f.field for f in fields_for_table(table.source_table)}
        mapped = {fm.source_field for fm in table.field_mappings}
        accounted_for = mapped | set(table.unmapped_source_fields)
        assert accounted_for == expected, f"{table.source_table} lost fields: {expected - accounted_for}"


def test_assembled_document_matches_expected_shape():
    """`assemble`'s output has the assignment's required top-level and per-table keys."""
    tables = _run_cold_pipeline()
    document = assemble(tables, generated_at="2026-08-21T00:00:00+00:00")

    assert document["mapping_version"] == "1.0"
    assert document["source"] == "legacy_hrm (MySQL)"
    assert document["destination"] == "people_platform (MongoDB)"
    assert len(document["tables"]) == 3
    for table in document["tables"]:
        for key in ("source_table", "destination_collection", "confidence", "reasoning",
                    "field_mappings", "unmapped_source_fields", "unmapped_destination_fields"):
            assert key in table
