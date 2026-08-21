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
    """Stage 4: map every field of one source table via one LLM call.

    Runs Stage 3 (candidate retrieval) then Stage 4 (adjudication) for a
    single table — this is the function `run_pipeline.py` calls once per
    table returned by `pipeline.align_tables.align_tables`.

    Args:
        source_table: e.g. "emp_master".
        dest_collection: e.g. "employees" — normally the collection
            `align_tables` matched to `source_table`.
        llm: `ClaudeLLMClient`, `OllamaLLMClient`, or
            `tests.fakes.FakeLLMClient`.
        embedder: `SentenceTransformerEmbedder` or
            `tests.fakes.FakeEmbedder`.
        top_k: Passed through to `top_k_candidates`.

    Returns:
        The LLM's raw response dict, with `source_table` and
        `destination_collection` added — ready for
        `pipeline.validate.validate_table_mapping`.

    Example:
        >>> from tests.fakes import FakeEmbedder, FakeLLMClient
        >>> raw = map_table("locations", "locations", FakeLLMClient(), FakeEmbedder())
        >>> raw["source_table"], raw["destination_collection"]
        ('locations', 'locations')
        >>> {fm["source_field"] for fm in raw["field_mappings"]} <= {
        ...     "loc_id", "loc_cd", "loc_nm", "city", "state_prov",
        ...     "country_cd", "postal_cd", "tz_cd"}
        True
    """
    source_fields = fields_for_table(source_table)
    dest_fields = fields_for_collection(dest_collection)
    candidates = top_k_candidates(source_fields, dest_fields, embedder, k=top_k)

    prompt = build_field_mapping_prompt(source_table, dest_collection, source_fields, candidates)
    result = llm.map_fields(prompt)
    result["source_table"] = source_table
    result["destination_collection"] = dest_collection
    return result
