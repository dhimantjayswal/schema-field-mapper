from pipeline.parse_schema import (
    dest_collections,
    fields_for_collection,
    fields_for_table,
    load_dest_fields,
    load_source_fields,
    source_tables,
)


def test_source_tables_match_assignment():
    assert source_tables() == ["emp_master", "dept_info", "locations"]


def test_dest_collections_match_assignment():
    assert dest_collections() == ["employees", "departments", "locations"]


def test_every_source_field_loaded():
    fields = load_source_fields()
    assert len(fields) == 19 + 7 + 8  # emp_master + dept_info + locations
    assert len(fields_for_table("emp_master")) == 19
    assert len(fields_for_table("dept_info")) == 7
    assert len(fields_for_table("locations")) == 8


def test_every_dest_field_loaded():
    fields = load_dest_fields()
    assert len(fields) == 25 + 7 + 8  # employees + departments + locations
    assert len(fields_for_collection("employees")) == 25
    assert len(fields_for_collection("departments")) == 7
    assert len(fields_for_collection("locations")) == 8


def test_comments_and_fks_survive_into_description():
    rec_stat = next(f for f in fields_for_table("emp_master") if f.field == "rec_stat")
    assert "A=Active" in rec_stat.description

    dept_id = next(f for f in fields_for_table("emp_master") if f.field == "dept_id")
    assert "dept_info.dept_id" in dept_id.description
