"""Stage 0 (schema loading) regression tests.

Pins the exact field counts per table/collection and the two schemas'
name/order against the assignment's own numbers (19+7+8 source fields,
25+7+8 destination fields) — a silent transcription slip in
`data/source_schema.py`/`data/dest_schema.py` would otherwise only surface
much later as a mysterious mapping gap. Also checks that comment/FK text
actually survives into `SourceField.description`, since Stage 3/4 read
that string, not the raw schema dict.
"""
from pipeline.parse_schema import (
    dest_collections,
    fields_for_collection,
    fields_for_table,
    load_dest_fields,
    load_source_fields,
    source_tables,
)


def test_source_tables_match_assignment():
    """`source_tables()` returns the assignment's 3 tables, in schema-definition order."""
    assert source_tables() == ["emp_master", "dept_info", "locations"]


def test_dest_collections_match_assignment():
    """`dest_collections()` returns the assignment's 3 collections, in schema-definition order."""
    assert dest_collections() == ["employees", "departments", "locations"]


def test_every_source_field_loaded():
    """`load_source_fields`/`fields_for_table` pick up the exact 19+7+8 field counts."""
    fields = load_source_fields()
    assert len(fields) == 19 + 7 + 8  # emp_master + dept_info + locations
    assert len(fields_for_table("emp_master")) == 19
    assert len(fields_for_table("dept_info")) == 7
    assert len(fields_for_table("locations")) == 8


def test_every_dest_field_loaded():
    """`load_dest_fields`/`fields_for_collection` pick up the exact 25+7+8 field counts."""
    fields = load_dest_fields()
    assert len(fields) == 25 + 7 + 8  # employees + departments + locations
    assert len(fields_for_collection("employees")) == 25
    assert len(fields_for_collection("departments")) == 7
    assert len(fields_for_collection("locations")) == 8


def test_comments_and_fks_survive_into_description():
    """`SourceField.description` includes the raw comment text and the FK target table."""
    rec_stat = next(f for f in fields_for_table("emp_master") if f.field == "rec_stat")
    assert "A=Active" in rec_stat.description

    dept_id = next(f for f in fields_for_table("emp_master") if f.field == "dept_id")
    assert "dept_info.dept_id" in dept_id.description
