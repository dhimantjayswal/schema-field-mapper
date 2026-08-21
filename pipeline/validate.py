"""Stage 5 — schema validation + completeness check. No LLM call.

Completeness (every source field ends up somewhere) is enforced here in
code against the Stage 0 ground truth, not trusted to the LLM's memory
across a multi-field batched call.
"""
from typing import Optional

from pydantic import BaseModel, Field

from pipeline.parse_schema import fields_for_collection, fields_for_table


class FieldMapping(BaseModel):
    source_field: str
    destination_field: str
    type_transform: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    notes: Optional[str] = None


class TableMapping(BaseModel):
    source_table: str
    destination_collection: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    field_mappings: list[FieldMapping]
    unmapped_source_fields: list[str] = []
    unmapped_destination_fields: list[str] = []


def validate_table_mapping(raw: dict, table_confidence: float, table_reasoning: str) -> TableMapping:
    table = TableMapping(
        source_table=raw["source_table"],
        destination_collection=raw["destination_collection"],
        confidence=table_confidence,
        reasoning=table_reasoning,
        field_mappings=raw.get("field_mappings", []),
        unmapped_source_fields=raw.get("unmapped_source_fields", []),
    )

    expected_source = {f.field for f in fields_for_table(table.source_table)}
    mapped_source = {fm.source_field for fm in table.field_mappings}
    declared_unmapped = set(table.unmapped_source_fields)
    forgotten = expected_source - mapped_source - declared_unmapped
    # Anything the LLM forgot to declare either way still ends up unmapped,
    # never silently dropped.
    table.unmapped_source_fields = sorted(declared_unmapped | forgotten)

    expected_dest = {f.path for f in fields_for_collection(table.destination_collection)}
    mapped_dest = {fm.destination_field for fm in table.field_mappings}
    table.unmapped_destination_fields = sorted(expected_dest - mapped_dest)

    return table
