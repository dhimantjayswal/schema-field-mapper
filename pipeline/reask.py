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
