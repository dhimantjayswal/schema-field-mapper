"""Prompt templates for Stage 4 (per-table field mapping) and Stage 7 (re-ask)."""
from pipeline.parse_schema import DestField, SourceField


def build_field_mapping_prompt(
    table: str,
    collection: str,
    fields: list[SourceField],
    candidates: dict[str, list[tuple[DestField, float]]],
) -> str:
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
            f"{d.path} ({d.type}{', ref -> ' + d.ref if d.ref else ''})"
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
        "Never force a low-quality match just to fill the array.",
        "",
        f"Return only fields for the {table} table. Do not reference any other "
        "table or collection.",
    ]
    return "\n".join(lines)


def build_reask_prompt(field_mapping) -> str:
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
