"""Dataset B — MongoDB people_platform.

Hand-transcribed from InterviewAssignment.docx, and pre-flattened to
dot-notation paths here (rather than as nested dicts + a runtime flattening
pass) — the nesting is static and small, so a generic flattener would be
solving a problem this input doesn't have. See WRITEUP.md.
"""

DEST_SCHEMA = {
    "database": "people_platform",
    "type": "MongoDB (Document)",
    "collections": {
        "employees": [
            {"path": "_id", "type": "ObjectId"},
            {"path": "employeeCode", "type": "String", "comment": "unique human-readable ID"},
            {"path": "fullName.firstName", "type": "String"},
            {"path": "fullName.lastName", "type": "String"},
            {"path": "employment.startDate", "type": "ISODate"},
            {"path": "employment.endDate", "type": "ISODate", "comment": "null if currently employed"},
            {"path": "employment.status", "type": "String", "comment": "active / inactive / terminated"},
            {"path": "employment.jobLevel", "type": "String", "comment": "e.g. L1, IC3, M1"},
            {"path": "employment.isRemote", "type": "Boolean"},
            {"path": "employment.managerId", "type": "ObjectId", "ref": "employees._id"},
            {"path": "compensation.baseSalary", "type": "Number"},
            {"path": "compensation.currency", "type": "String", "comment": "ISO 4217"},
            {"path": "contact.email", "type": "String"},
            {"path": "contact.phone", "type": "String"},
            {"path": "department.departmentId", "type": "ObjectId", "ref": "departments._id"},
            {"path": "department.code", "type": "String"},
            {"path": "department.name", "type": "String"},
            {"path": "location.locationId", "type": "ObjectId", "ref": "locations._id"},
            {"path": "location.code", "type": "String"},
            {"path": "location.name", "type": "String"},
            {"path": "location.city", "type": "String"},
            {"path": "location.country", "type": "String", "comment": "ISO 3166-1 alpha-2"},
            {"path": "location.timezone", "type": "String"},
            {"path": "meta.createdAt", "type": "ISODate"},
            {"path": "meta.updatedAt", "type": "ISODate"},
        ],
        "departments": [
            {"path": "_id", "type": "ObjectId"},
            {"path": "code", "type": "String"},
            {"path": "name", "type": "String"},
            {"path": "parentDepartmentId", "type": "ObjectId", "ref": "departments._id",
             "comment": "self-ref"},
            {"path": "headEmployeeId", "type": "ObjectId", "ref": "employees._id"},
            {"path": "costCenterCode", "type": "String"},
            {"path": "isActive", "type": "Boolean"},
        ],
        "locations": [
            {"path": "_id", "type": "ObjectId"},
            {"path": "code", "type": "String"},
            {"path": "name", "type": "String"},
            {"path": "city", "type": "String"},
            {"path": "stateOrProvince", "type": "String"},
            {"path": "country", "type": "String", "comment": "ISO 3166-1 alpha-2"},
            {"path": "postalCode", "type": "String"},
            {"path": "timezone", "type": "String"},
        ],
    },
}
