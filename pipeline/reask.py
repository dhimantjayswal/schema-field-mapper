"""Stage 7 — low-confidence re-ask (self-consistency).

Only fields below the confidence threshold get a second, differently-framed
single-field call. Expected to fire rarely given how close these two
schemas are semantically — see WRITEUP.md's "hard fields" section for the
cases it actually exists for.
"""
from pipeline.llm_client import LLMClient
from pipeline.prompts import build_reask_prompt
from pipeline.validate import FieldMapping, TableMapping


def reask_low_confidence(
    table: TableMapping,
    llm: LLMClient,
    threshold: float = 0.7,
) -> TableMapping:
    """Stage 7: re-ask the LLM for any field mapping below `threshold`.

    Fields at or above `threshold` pass through untouched — this only
    spends extra LLM calls on the mappings the pipeline is least sure
    about. If a re-ask response comes back empty (no `field_mappings`),
    the original low-confidence mapping is kept rather than dropped.

    Args:
        table: A validated `TableMapping` from `validate_table_mapping`.
        llm: `ClaudeLLMClient`, `OllamaLLMClient`, or
            `tests.fakes.FakeLLMClient`.
        threshold: Fields with `confidence < threshold` get re-asked.

    Returns:
        `table`, mutated in place and returned for convenience —
        `field_mappings` replaced with the revised list.

    Example:
        >>> from pipeline.validate import FieldMapping, TableMapping
        >>> class AlwaysConfidentLLM:
        ...     def map_fields(self, prompt):
        ...         return {"field_mappings": [{
        ...             "source_field": "job_lvl_cd", "destination_field": "employment.jobLevel",
        ...             "type_transform": "String", "confidence": 0.95,
        ...             "reasoning": "revised on re-ask", "notes": None,
        ...         }]}
        >>> table = TableMapping(
        ...     source_table="emp_master", destination_collection="employees",
        ...     confidence=0.9, reasoning="ok",
        ...     field_mappings=[FieldMapping(
        ...         source_field="job_lvl_cd", destination_field="employment.jobLevel",
        ...         type_transform="String", confidence=0.4, reasoning="unsure")],
        ... )
        >>> revised = reask_low_confidence(table, AlwaysConfidentLLM(), threshold=0.7)
        >>> revised.field_mappings[0].confidence
        0.95
    """
    revised = []
    for fm in table.field_mappings:
        if fm.confidence >= threshold:
            revised.append(fm)
            continue
        result = llm.map_fields(build_reask_prompt(fm))
        candidates = result.get("field_mappings", [])
        revised.append(FieldMapping(**candidates[0]) if candidates else fm)
    table.field_mappings = revised
    return table
