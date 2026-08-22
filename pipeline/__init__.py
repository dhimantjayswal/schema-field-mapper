"""The Stage 0-7 field-mapping pipeline: `parse_schema` -> `align_tables` ->
`embed_candidates` -> `map_fields` -> `validate` -> `assemble` -> `reask`,
plus supporting modules (`llm_client`, `prompts`, `names`, `lexicon`,
`roles`, `evaluate`). Driven end-to-end by `run_pipeline.py`; see
WRITEUP.md for the stage-by-stage design rationale.
"""
