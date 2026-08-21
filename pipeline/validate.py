"""Stage 5 — schema validation + completeness check. No LLM call.

Completeness (every source field ends up somewhere) is enforced here in
code against the Stage 0 ground truth, not trusted to the LLM's memory
across a multi-field batched call.
"""
from typing import Optional

from pydantic import BaseModel, Field

from pipeline.parse_schema import fields_for_collection, fields_for_table


class FieldMapping(BaseModel):
    """One entry of `TableMapping.field_mappings` — matches the assignment's
    exact required shape for a single source-to-destination field mapping.

    Example:
        >>> FieldMapping(source_field="is_remote", destination_field="employment.isRemote",
        ...               type_transform="TINYINT(1) -> Boolean", confidence=0.99,
        ...               reasoning="Direct boolean cast.")
        FieldMapping(source_field='is_remote', destination_field='employment.isRemote', type_transform='TINYINT(1) -> Boolean', confidence=0.99, reasoning='Direct boolean cast.', notes=None)
        >>> FieldMapping(source_field="x", destination_field="y", type_transform="z",
        ...               confidence=1.5, reasoning="bad")  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ...
        pydantic_core._pydantic_core.ValidationError: 1 validation error for FieldMapping
        ...
    """

    source_field: str
    destination_field: str
    type_transform: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    notes: Optional[str] = None


class TableMapping(BaseModel):
    """One entry of the final document's `tables[]` — matches the
    assignment's exact required shape for one source-table-to-destination-
    collection mapping. Built by `validate_table_mapping`, not constructed
    directly outside tests.
    """

    source_table: str
    destination_collection: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    field_mappings: list[FieldMapping]
    unmapped_source_fields: list[str] = []
    unmapped_destination_fields: list[str] = []


def validate_table_mapping(raw: dict, table_confidence: float, table_reasoning: str) -> TableMapping:
    """Stage 5: validate one table's LLM response and fill in completeness.

    Two things happen here that the LLM call itself can't guarantee:
    schema validation (via Pydantic — malformed confidence, missing keys,
    etc. raise immediately) and completeness (any source field the LLM's
    response neither mapped nor declared unmapped is added to
    `unmapped_source_fields` anyway, so nothing is silently dropped even
    if the LLM's batched response missed one).

    Args:
        raw: `pipeline.map_fields.map_table`'s return value — must have
            `source_table`, `destination_collection`, `field_mappings`,
            `unmapped_source_fields` keys.
        table_confidence: From `pipeline.align_tables.align_tables`'s
            Stage 1 alignment for this table (Stage 5 doesn't compute its
            own table-level confidence — that's Stage 1's job).
        table_reasoning: Likewise, from Stage 1.

    Returns:
        A validated `TableMapping` with `unmapped_source_fields` and
        `unmapped_destination_fields` both recomputed against ground truth.

    Example:
        >>> raw = {
        ...     "source_table": "locations", "destination_collection": "locations",
        ...     "field_mappings": [{
        ...         "source_field": "loc_id", "destination_field": "_id",
        ...         "type_transform": "INT -> ObjectId", "confidence": 0.9,
        ...         "reasoning": "primary key", "notes": None,
        ...     }],
        ...     "unmapped_source_fields": [],
        ... }
        >>> table = validate_table_mapping(raw, table_confidence=0.9, table_reasoning="ok")
        >>> "loc_cd" in table.unmapped_source_fields  # the LLM forgot it; caught here
        True
        >>> "loc_id" in table.unmapped_source_fields  # correctly mapped, not double-counted
        False
    """
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
