"""Rule-based structural role classifier.

Cheap, deterministic role signal folded into field descriptions (Stage 0/3)
so both the embedder and the LLM see it. This is specifically what's meant
to separate `hire_dt` (a business date) from `created_ts` (an audit
timestamp): both are DATETIME, both tokenize to date/timestamp-ish words,
and only the *role* actually distinguishes them — a real ambiguity that
caused a wrong mapping in an earlier real run (see WRITEUP.md).
"""
from typing import Optional

from pipeline.names import tokenize

_AUDIT_HINTS = {"created", "updated", "modified"}
_MONEY_HINTS = {"sal", "salary", "amt", "amount", "price", "cost"}
_CONTACT_HINTS = {"email", "phone", "contact"}

def classify_role(
    name: str,
    type_str: str,
    comment: Optional[str] = None,
    pk: bool = False,
    fk: Optional[str] = None,
) -> str:
    """Classify a field's structural role from its name, type, and flags.

    Args:
        name: The bare field/column name (last path segment for dest fields).
        type_str: Raw type string, e.g. "DATETIME", "CHAR(1)", "ObjectId".
        comment: Inline comment, if any — checked for enum-style value lists
            (`"A=Active, I=Inactive"`) to distinguish an enum code from
            ordinary free text.
        pk: True if this is a primary key.
        fk: FK/ref target (`"table.column"`), if this is a foreign key.

    Returns:
        One of "identifier", "foreign_key", "timestamp_audit", "timestamp_business",
        "enum_code", "boolean_flag", "money", "contact", "freetext".

    Example:
        >>> classify_role("hire_dt", "DATETIME")
        'timestamp_business'
        >>> classify_role("created_ts", "DATETIME")
        'timestamp_audit'
        >>> classify_role("rec_stat", "CHAR(1)", comment="A=Active, I=Inactive, T=Terminated")
        'enum_code'
        >>> classify_role("is_remote", "TINYINT(1)")
        'boolean_flag'
        >>> classify_role("emp_id", "INT", pk=True)
        'identifier'
        >>> classify_role("dept_id", "INT", fk="dept_info.dept_id")
        'foreign_key'
        >>> classify_role("base_sal", "DECIMAL(12,2)")
        'money'
        >>> classify_role("work_email", "VARCHAR(120)")
        'contact'
        >>> classify_role("dept_nm", "VARCHAR(100)")
        'freetext'
    """
    tokens = set(tokenize(name))
    type_upper = type_str.upper()

    if pk or name.lower() in ("_id", "id"):
        return "identifier"
    if fk:
        return "foreign_key"
    if "BOOLEAN" in type_upper or "TINYINT(1)" in type_upper:
        return "boolean_flag"
    if "CHAR" in type_upper and "VARCHAR" not in type_upper and comment and "=" in comment:
        return "enum_code"
    if "DATE" in type_upper or "TIME" in type_upper:
        return "timestamp_audit" if tokens & _AUDIT_HINTS else "timestamp_business"
    if tokens & _MONEY_HINTS or "DECIMAL" in type_upper:
        return "money"
    if tokens & _CONTACT_HINTS:
        return "contact"
    return "freetext"
