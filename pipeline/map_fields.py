"""Stage 4 — per-table LLM adjudication.

One Claude call per source table, given that table's fields plus each
field's pre-retrieved candidates only — never the sibling tables, never the
raw destination schema dump. This is the stage the assignment's constraint
is actually about.
"""
from pipeline.embed_candidates import Embedder, top_k_candidates
from pipeline.llm_client import LLMClient
from pipeline.parse_schema import fields_for_collection, fields_for_table
from pipeline.prompts import build_field_mapping_prompt


def map_table(
    source_table: str,
    dest_collection: str,
    llm: LLMClient,
    embedder: Embedder,
    top_k: int = 5,
) -> dict:
    source_fields = fields_for_table(source_table)
    dest_fields = fields_for_collection(dest_collection)
    candidates = top_k_candidates(source_fields, dest_fields, embedder, k=top_k)

    prompt = build_field_mapping_prompt(source_table, dest_collection, source_fields, candidates)
    result = llm.map_fields(prompt)
    result["source_table"] = source_table
    result["destination_collection"] = dest_collection
    return result
