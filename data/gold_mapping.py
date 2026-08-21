"""Hand-curated gold mapping — ground truth for accuracy evaluation.

Written from the assignment's own schemas and semantics, not derived from
anything this pipeline has ever produced — evaluating a pipeline against
its own output would be circular. `expected: None` marks the one field
(`dob`) with no destination concept at all; getting that case right is
worth more than the other 33 combined, since forcing a wrong match there
is a silent-data-corruption bug in a real migration, not a rounding error.
"""

GOLD_MAPPING = {
    "emp_master": {
        "emp_id": {"expected": "_id", "alternatives": [], "difficulty": "medium",
                   "rationale": "ID strategy; legacy id retention"},
        "emp_cd": {"expected": "employeeCode", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "f_name": {"expected": "fullName.firstName", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "l_name": {"expected": "fullName.lastName", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "dob": {"expected": None, "alternatives": [], "difficulty": "hard",
                "rationale": "No target concept — the key negative case"},
        "hire_dt": {"expected": "employment.startDate", "alternatives": [], "difficulty": "medium",
                    "rationale": "vs meta.createdAt"},
        "term_dt": {"expected": "employment.endDate", "alternatives": [], "difficulty": "medium", "rationale": ""},
        "dept_id": {"expected": "department.departmentId", "alternatives": ["department.code"],
                    "difficulty": "medium", "rationale": "alt: department.code"},
        "mgr_emp_id": {"expected": "employment.managerId", "alternatives": [], "difficulty": "medium",
                       "rationale": "self-ref, two-pass load"},
        "job_lvl_cd": {"expected": "employment.jobLevel", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "base_sal": {"expected": "compensation.baseSalary", "alternatives": [], "difficulty": "easy",
                     "rationale": "precision note required"},
        "sal_currency": {"expected": "compensation.currency", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "work_email": {"expected": "contact.email", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "work_phone": {"expected": "contact.phone", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "office_loc_id": {"expected": "location.locationId", "alternatives": [], "difficulty": "medium", "rationale": ""},
        "is_remote": {"expected": "employment.isRemote", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "rec_stat": {"expected": "employment.status", "alternatives": [], "difficulty": "medium",
                     "rationale": "enum transform"},
        "created_ts": {"expected": "meta.createdAt", "alternatives": [], "difficulty": "medium", "rationale": "vs hire_dt"},
        "updated_ts": {"expected": "meta.updatedAt", "alternatives": [], "difficulty": "easy", "rationale": ""},
    },
    "dept_info": {
        "dept_id": {"expected": "_id", "alternatives": [], "difficulty": "medium", "rationale": ""},
        "dept_cd": {"expected": "code", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "dept_nm": {"expected": "name", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "parent_dept_id": {"expected": "parentDepartmentId", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "dept_head_id": {"expected": "headEmployeeId", "alternatives": [], "difficulty": "medium", "rationale": ""},
        "cost_ctr_cd": {"expected": "costCenterCode", "alternatives": [], "difficulty": "medium",
                        "rationale": "abbreviation density"},
        "dept_stat": {"expected": "isActive", "alternatives": [], "difficulty": "hard",
                      "rationale": "lossy CHAR->Boolean"},
    },
    "locations": {
        "loc_id": {"expected": "_id", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "loc_cd": {"expected": "code", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "loc_nm": {"expected": "name", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "city": {"expected": "city", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "state_prov": {"expected": "stateOrProvince", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "country_cd": {"expected": "country", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "postal_cd": {"expected": "postalCode", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "tz_cd": {"expected": "timezone", "alternatives": [], "difficulty": "easy", "rationale": ""},
    },
}
