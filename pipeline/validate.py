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


def _resolve_conflicts(field_mappings: list[FieldMapping]) -> tuple[list[FieldMapping], list[str]]:
    """Deduplicate competing claims on the same `destination_field`.

    A batched per-table LLM call has no visibility into what it already
    assigned to other fields in the same response, so two source fields
    can each independently — and each plausibly — claim the same
    destination. A real run hit exactly this: `dob` and `created_ts` both
    got mapped to `meta.createdAt` (confidences 0.7 and 0.8). Left
    unresolved, both would sit in the delivered output as if valid.

    Resolution is greedy highest-confidence-wins, not a full assignment
    solve (e.g. Hungarian/`scipy.optimize.linear_sum_assignment`): at this
    schema's scale (34 fields), a real conflict is rare and isolated, so
    a global optimum over the whole conflict graph buys nothing a local
    per-destination comparison doesn't already get for free. Revisit if a
    much larger schema starts producing chained conflicts.

    Args:
        field_mappings: The (unvalidated-for-conflicts) mappings for one table.

    Returns:
        `(kept, demoted_source_fields)` — `kept` has at most one mapping
        per `destination_field`; `demoted_source_fields` are the losers'
        `source_field` names, meant to be folded into
        `unmapped_source_fields` rather than silently dropped.

    Example:
        >>> mappings = [
        ...     FieldMapping(source_field="dob", destination_field="meta.createdAt",
        ...                  type_transform="DATE", confidence=0.7, reasoning="guess"),
        ...     FieldMapping(source_field="created_ts", destination_field="meta.createdAt",
        ...                  type_transform="DATETIME", confidence=0.8, reasoning="clear match"),
        ... ]
        >>> kept, demoted = _resolve_conflicts(mappings)
        >>> [fm.source_field for fm in kept]
        ['created_ts']
        >>> demoted
        ['dob']
    """
    best_by_target: dict[str, FieldMapping] = {}
    for fm in field_mappings:
        champion = best_by_target.get(fm.destination_field)
        if champion is None or fm.confidence > champion.confidence:
            best_by_target[fm.destination_field] = fm

    kept = [fm for fm in field_mappings if best_by_target[fm.destination_field] is fm]
    kept_source_fields = {fm.source_field for fm in kept}
    demoted = [fm.source_field for fm in field_mappings if fm.source_field not in kept_source_fields]
    return kept, demoted


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

    Three things happen here that the LLM call itself can't guarantee:
    schema validation (via Pydantic — malformed confidence, missing keys,
    etc. raise immediately), conflict resolution (`_resolve_conflicts` —
    two source fields can't both keep the same `destination_field`), and
    completeness (any source field neither mapped nor declared unmapped —
    including one just demoted by conflict resolution — is added to
    `unmapped_source_fields`, so nothing is silently dropped).

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

    table.field_mappings, demoted = _resolve_conflicts(table.field_mappings)

    expected_source = {f.field for f in fields_for_table(table.source_table)}
    mapped_source = {fm.source_field for fm in table.field_mappings}
    declared_unmapped = set(table.unmapped_source_fields) | set(demoted)
    forgotten = expected_source - mapped_source - declared_unmapped
    # Anything the LLM forgot to declare either way still ends up unmapped,
    # never silently dropped.
    table.unmapped_source_fields = sorted(declared_unmapped | forgotten)

    expected_dest = {f.path for f in fields_for_collection(table.destination_collection)}
    mapped_dest = {fm.destination_field for fm in table.field_mappings}
    table.unmapped_destination_fields = sorted(expected_dest - mapped_dest)

    return table
