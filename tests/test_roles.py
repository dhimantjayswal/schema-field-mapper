"""Exhaustive, table-driven role classification over all 34 real source
fields — not representative sampling. This is the regression net for the
retrieval stage's role signal: if `cost_ctr_cd`'s role silently changes,
every downstream candidate score for it shifts without anyone noticing
unless this test catches it.
"""
import pytest

from pipeline.parse_schema import load_source_fields

EXPECTED_ROLES = {
    ("emp_master", "emp_id"): "identifier",
    ("emp_master", "emp_cd"): "freetext",
    ("emp_master", "f_name"): "freetext",
    ("emp_master", "l_name"): "freetext",
    ("emp_master", "dob"): "timestamp_business",
    ("emp_master", "hire_dt"): "timestamp_business",
    ("emp_master", "term_dt"): "timestamp_business",
    ("emp_master", "dept_id"): "foreign_key",
    ("emp_master", "mgr_emp_id"): "foreign_key",
    ("emp_master", "job_lvl_cd"): "freetext",
    ("emp_master", "base_sal"): "money",
    ("emp_master", "sal_currency"): "money",
    ("emp_master", "work_email"): "contact",
    ("emp_master", "work_phone"): "contact",
    ("emp_master", "office_loc_id"): "foreign_key",
    ("emp_master", "is_remote"): "boolean_flag",
    ("emp_master", "rec_stat"): "enum_code",
    ("emp_master", "created_ts"): "timestamp_audit",
    ("emp_master", "updated_ts"): "timestamp_audit",
    ("dept_info", "dept_id"): "identifier",
    ("dept_info", "dept_cd"): "freetext",
    ("dept_info", "dept_nm"): "freetext",
    ("dept_info", "parent_dept_id"): "foreign_key",
    ("dept_info", "dept_head_id"): "foreign_key",
    ("dept_info", "cost_ctr_cd"): "money",
    ("dept_info", "dept_stat"): "enum_code",
    ("locations", "loc_id"): "identifier",
    ("locations", "loc_cd"): "freetext",
    ("locations", "loc_nm"): "freetext",
    ("locations", "city"): "freetext",
    ("locations", "state_prov"): "freetext",
    ("locations", "country_cd"): "freetext",
    ("locations", "postal_cd"): "freetext",
    ("locations", "tz_cd"): "freetext",
}


def test_expected_roles_cover_every_source_field():
    """`EXPECTED_ROLES` has exactly one entry per real source field — no gaps, no stale extras."""
    all_fields = {(f.table, f.field) for f in load_source_fields()}
    assert set(EXPECTED_ROLES) == all_fields


@pytest.mark.parametrize("table,field", list(EXPECTED_ROLES))
def test_role_matches_expected(table, field):
    """`classify_role` (via `SourceField.role`) matches the expected role for this exact field."""
    f = next(f for f in load_source_fields() if f.table == table and f.field == field)
    assert f.role == EXPECTED_ROLES[(table, field)]


def test_hire_dt_and_created_ts_get_different_roles():
    """The real ambiguity role classification exists to resolve: both are
    DATETIME with no comment, and only the name (business vs. audit
    language) tells them apart."""
    fields = {f.field: f for f in load_source_fields() if f.table == "emp_master"}
    assert fields["hire_dt"].role == "timestamp_business"
    assert fields["created_ts"].role == "timestamp_audit"
    assert fields["hire_dt"].role != fields["created_ts"].role
