"""Dataset A — MySQL legacy_hrm.

Hand-transcribed from InterviewAssignment.docx. Transcribing once into a
clean literal (rather than parsing the docx's pseudo-DDL text at runtime)
is the deliberate choice — see WRITEUP.md.
"""

SOURCE_SCHEMA = {
    "database": "legacy_hrm",
    "type": "MySQL (Relational)",
    "tables": {
        "emp_master": [
            {"field": "emp_id", "type": "INT", "pk": True},
            {"field": "emp_cd", "type": "VARCHAR(20)", "unique": True, "nullable": False,
             "comment": "human-readable employee code"},
            {"field": "f_name", "type": "VARCHAR(50)", "nullable": False},
            {"field": "l_name", "type": "VARCHAR(50)", "nullable": False},
            {"field": "dob", "type": "DATE"},
            {"field": "hire_dt", "type": "DATETIME"},
            {"field": "term_dt", "type": "DATETIME", "comment": "null if still active"},
            {"field": "dept_id", "type": "INT", "fk": "dept_info.dept_id"},
            {"field": "mgr_emp_id", "type": "INT", "fk": "emp_master.emp_id"},
            {"field": "job_lvl_cd", "type": "VARCHAR(10)", "comment": "e.g. L1, L2, IC3, M1"},
            {"field": "base_sal", "type": "DECIMAL(12,2)"},
            {"field": "sal_currency", "type": "CHAR(3)", "comment": "ISO 4217, e.g. USD"},
            {"field": "work_email", "type": "VARCHAR(120)", "unique": True},
            {"field": "work_phone", "type": "VARCHAR(20)"},
            {"field": "office_loc_id", "type": "INT", "fk": "locations.loc_id"},
            {"field": "is_remote", "type": "TINYINT(1)", "comment": "0 or 1"},
            {"field": "rec_stat", "type": "CHAR(1)", "comment": "A=Active, I=Inactive, T=Terminated"},
            {"field": "created_ts", "type": "DATETIME", "comment": "record creation timestamp"},
            {"field": "updated_ts", "type": "DATETIME", "comment": "last update timestamp"},
        ],
        "dept_info": [
            {"field": "dept_id", "type": "INT", "pk": True},
            {"field": "dept_cd", "type": "VARCHAR(20)", "unique": True},
            {"field": "dept_nm", "type": "VARCHAR(100)"},
            {"field": "parent_dept_id", "type": "INT", "fk": "dept_info.dept_id",
             "comment": "self-referencing"},
            {"field": "dept_head_id", "type": "INT", "fk": "emp_master.emp_id"},
            {"field": "cost_ctr_cd", "type": "VARCHAR(20)", "comment": "finance cost center code"},
            {"field": "dept_stat", "type": "CHAR(1)", "comment": "A=Active, I=Inactive"},
        ],
        "locations": [
            {"field": "loc_id", "type": "INT", "pk": True},
            {"field": "loc_cd", "type": "VARCHAR(20)", "unique": True},
            {"field": "loc_nm", "type": "VARCHAR(100)"},
            {"field": "city", "type": "VARCHAR(80)"},
            {"field": "state_prov", "type": "VARCHAR(80)"},
            {"field": "country_cd", "type": "CHAR(2)", "comment": "ISO 3166-1 alpha-2"},
            {"field": "postal_cd", "type": "VARCHAR(20)"},
            {"field": "tz_cd", "type": "VARCHAR(50)", "comment": "IANA timezone"},
        ],
    },
}
