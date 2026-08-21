"""Stage 6 — assemble the final mapping document. Pure code, no LLM call."""
from datetime import datetime, timezone
from typing import Optional

from pipeline.validate import TableMapping


def assemble(tables: list[TableMapping], generated_at: Optional[str] = None) -> dict:
    """Stage 6: merge validated per-table results into the final document.

    Pure code, no LLM call — matches the assignment's required top-level
    shape exactly (`mapping_version`, `source`, `destination`,
    `generated_at`, `tables[]`).

    Args:
        tables: Validated `TableMapping`s, one per source table — normally
            `[reask_low_confidence(validate_table_mapping(...)) for ...]`.
        generated_at: ISO 8601 timestamp; defaults to now (UTC). Pass an
            explicit value for reproducible output (tests, this docstring).

    Returns:
        The complete mapping document, JSON-serializable as-is via
        `json.dumps`.

    Example:
        >>> from pipeline.validate import TableMapping
        >>> table = TableMapping(source_table="locations", destination_collection="locations",
        ...                      confidence=0.9, reasoning="ok", field_mappings=[])
        >>> doc = assemble([table], generated_at="2026-08-21T00:00:00+00:00")
        >>> doc["mapping_version"], doc["source"], doc["generated_at"]
        ('1.0', 'legacy_hrm (MySQL)', '2026-08-21T00:00:00+00:00')
        >>> doc["tables"][0]["source_table"]
        'locations'
    """
    return {
        "mapping_version": "1.0",
        "source": "legacy_hrm (MySQL)",
        "destination": "people_platform (MongoDB)",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "tables": [t.model_dump() for t in tables],
    }
