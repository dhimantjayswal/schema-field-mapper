"""Prompt templates for Stage 4 (per-table field mapping) and Stage 7 (re-ask).

Kept as plain string-building functions rather than a templating library
(Jinja2 etc.) — two templates, no conditionals a human wouldn't write
inline, not worth a dependency.
"""
from pipeline.parse_schema import DestField, SourceField


def build_field_mapping_prompt(
    table: str,
    collection: str,
    fields: list[SourceField],
    candidates: dict[str, list[tuple[DestField, float]]],
) -> str:
    """Build the Stage 4 prompt for one source table.

    Deliberately scoped to one table: only `fields` (that table's columns)
    and their pre-retrieved `candidates` are included — never the sibling
    tables or the raw destination schema. This is the prompt the
    assignment's "no both schemas in one call" constraint is actually
    about; see WRITEUP.md for the full reasoning.

    Args:
        table: Source table name, e.g. "emp_master".
        collection: Destination collection name, e.g. "employees".
        fields: That table's fields — typically `fields_for_table(table)`.
        candidates: Per-field candidate lists from
            `pipeline.embed_candidates.top_k_candidates`.

    Returns:
        The full prompt text, ready to pass to `LLMClient.map_fields`.

    The `role` shown per field (`pipeline.roles.classify_role`) is what's
    meant to stop the model defaulting to "both are dates" reasoning — see
    the worked `NO_MATCH` example below, which exists for the same reason.

    Example:
        >>> from pipeline.parse_schema import SourceField, DestField
        >>> fields = [SourceField(table="locations", field="tz_cd", type="VARCHAR(50)",
        ...                       comment="IANA timezone")]
        >>> candidates = {"tz_cd": [(DestField(collection="locations", path="timezone",
        ...                                    type="String"), 0.66)]}
        >>> prompt = build_field_mapping_prompt("locations", "locations", fields, candidates)
        >>> print(prompt.splitlines()[2])
        SOURCE TABLE: locations (legacy_hrm, MySQL)
        >>> "tz_cd -> candidates: [timezone (String, role: freetext)]" in prompt
        True
    """
    lines = [
        "You are mapping fields from a MySQL table to their MongoDB destination.",
        "",
        f"SOURCE TABLE: {table} (legacy_hrm, MySQL)",
        "Fields:",
    ]
    for f in fields:
        bits = [f"- {f.field}: {f.type}"]
        if f.pk:
            bits.append("PRIMARY KEY")
        if f.fk:
            bits.append(f"FK -> {f.fk}")
        bits.append(f"role: {f.role}")
        line = " ".join(bits)
        if f.comment:
            line += f" — {f.comment}"
        lines.append(line)

    lines += [
        "",
        f"DESTINATION COLLECTION: {collection} (people_platform, MongoDB)",
        "Candidate destination fields per source field (pre-retrieved by embedding",
        "similarity — pick the best one, or none if nothing truly matches):",
    ]
    for f in fields:
        cand_strs = [
            f"{d.path} ({d.type}, role: {d.role}{', ref -> ' + d.ref if d.ref else ''})"
            for d, _score in candidates.get(f.field, [])
        ]
        lines.append(f"- {f.field} -> candidates: [{', '.join(cand_strs)}]")

    lines += [
        "",
        "For each source field return exactly one object with: source_field, "
        "destination_field, type_transform, confidence (0-1), reasoning (one "
        "plain-English sentence), notes (value-transform logic, e.g. a code "
        "lookup table, or null if none is needed).",
        "",
        "If no candidate is a genuine match, do not include that field in "
        "field_mappings — list its name in unmapped_source_fields instead. "
        "Never force a low-quality match just to fill the array. Two fields "
        "must never share the same destination_field within this response.",
        "",
        "Worked example of a correct NO_MATCH decision — do not repeat this "
        "mistake: a source field 'dob' (DATE, \"date of birth\") has "
        "candidates including 'employment.startDate' and 'meta.createdAt' — "
        "both are dates, but neither represents a birth date. The correct "
        "answer is to leave 'dob' out of field_mappings entirely and list it "
        "in unmapped_source_fields, NOT to map it to a same-typed field just "
        "because both happen to be dates.",
        "",
        f"Return only fields for the {table} table. Do not reference any other "
        "table or collection.",
    ]
    return "\n".join(lines)


def build_reask_prompt(field_mapping) -> str:
    """Build the Stage 7 prompt re-examining one low-confidence field mapping.

    Args:
        field_mapping: A `pipeline.validate.FieldMapping` whose `confidence`
            fell below `reask_low_confidence`'s threshold.

    Returns:
        The re-ask prompt text.

    Example:
        >>> from pipeline.validate import FieldMapping
        >>> fm = FieldMapping(source_field="job_lvl_cd", destination_field="employment.jobLevel",
        ...                    type_transform="VARCHAR -> String", confidence=0.5,
        ...                    reasoning="uncertain guess")
        >>> prompt = build_reask_prompt(fm)
        >>> "0.50 confidence" in prompt
        True
        >>> "source_field: job_lvl_cd" in prompt
        True
    """
    return (
        "Re-examine this single field mapping — it previously scored "
        f"{field_mapping.confidence:.2f} confidence, below the reliability "
        "threshold for this pipeline.\n\n"
        f"source_field: {field_mapping.source_field}\n"
        f"destination_field: {field_mapping.destination_field}\n"
        f"type_transform: {field_mapping.type_transform}\n"
        f"reasoning: {field_mapping.reasoning}\n\n"
        "Reconsider from scratch and return a revised field_mappings array "
        "containing a single entry with the same shape (source_field, "
        "destination_field, type_transform, confidence, reasoning, notes)."
    )
