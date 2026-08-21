#!/usr/bin/env python3
"""CLI entrypoint — runs Stages 0-7 end to end and writes output/mapping.json.

Requires ANTHROPIC_API_KEY (Stage 4 / 7 make real Claude calls). Everything
else runs locally: table alignment (Stage 1) is a heuristic, candidate
retrieval (Stage 3) is a local sentence-transformers model, validation
(Stage 5) and assembly (Stage 6) are pure code.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from pipeline.align_tables import align_tables
from pipeline.assemble import assemble
from pipeline.embed_candidates import SentenceTransformerEmbedder
from pipeline.llm_client import ClaudeLLMClient
from pipeline.map_fields import map_table
from pipeline.reask import reask_low_confidence
from pipeline.validate import validate_table_mapping

OUTPUT_PATH = Path(__file__).parent / "output" / "mapping.json"


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Map legacy_hrm fields to people_platform.")
    parser.add_argument("--top-k", type=int, default=5, help="candidates retrieved per source field")
    parser.add_argument("--confidence-threshold", type=float, default=0.7,
                         help="fields below this trigger a Stage 7 re-ask")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    embedder = SentenceTransformerEmbedder()
    llm = ClaudeLLMClient()

    tables = []
    for alignment in align_tables():
        raw = map_table(
            alignment["source_table"], alignment["destination_collection"],
            llm, embedder, top_k=args.top_k,
        )
        table = validate_table_mapping(raw, alignment["confidence"], alignment["reasoning"])
        table = reask_low_confidence(table, llm, threshold=args.confidence_threshold)
        tables.append(table)

        if args.verbose:
            print(
                f"{table.source_table} -> {table.destination_collection}: "
                f"{len(table.field_mappings)} mapped, "
                f"{len(table.unmapped_source_fields)} unmapped "
                f"(table confidence {table.confidence:.2f})"
            )

    document = assemble(tables)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(document, indent=2))
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
