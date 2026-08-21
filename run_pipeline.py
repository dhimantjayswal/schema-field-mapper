#!/usr/bin/env python3
"""CLI entrypoint — runs Stages 0-7 end to end and writes output/mapping.json.

Stage 4/7 need an LLM: Claude (ANTHROPIC_API_KEY, the primary design
target) or a local Ollama model (no key, no cost — auto-selected when no
key is set). Everything else runs locally regardless: table alignment
(Stage 1) is a heuristic, candidate retrieval (Stage 3) is a local
sentence-transformers model, validation (Stage 5) and assembly (Stage 6)
are pure code.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from pipeline.align_tables import align_tables
from pipeline.assemble import assemble
from pipeline.embed_candidates import SentenceTransformerEmbedder
from pipeline.llm_client import ClaudeLLMClient, OllamaLLMClient
from pipeline.map_fields import map_table
from pipeline.reask import reask_low_confidence
from pipeline.validate import validate_table_mapping

OUTPUT_PATH = Path(__file__).parent / "output" / "mapping.json"


def main() -> int:
    """Run Stages 0-7 end to end and write `output/mapping.json`.

    LLM backend selection: `--llm-backend claude` or `--llm-backend
    ollama` forces one; omit it and the pipeline uses Claude if
    `ANTHROPIC_API_KEY` is set (in the environment or `.env`), else falls
    back to a local Ollama model (`--ollama-model`, default `qwen2.5:7b`)
    with no key needed at all.

    Returns:
        `0` — a process exit code, per the `sys.exit(main())` convention
        at the bottom of this file.

    Example:
        $ python run_pipeline.py --verbose
        LLM backend: ollama (qwen2.5:7b)
        emp_master -> employees: 19 mapped, 0 unmapped (table confidence 0.92)
        dept_info -> departments: 6 mapped, 1 unmapped (table confidence 0.88)
        locations -> locations: 7 mapped, 1 unmapped (table confidence 0.90)

        Wrote /path/to/ibm_assignment/output/mapping.json

        $ python run_pipeline.py --llm-backend claude --top-k 8 --confidence-threshold 0.8
    """
    load_dotenv()

    parser = argparse.ArgumentParser(description="Map legacy_hrm fields to people_platform.")
    parser.add_argument("--top-k", type=int, default=5, help="candidates retrieved per source field")
    parser.add_argument("--confidence-threshold", type=float, default=0.7,
                         help="fields below this trigger a Stage 7 re-ask")
    parser.add_argument("--llm-backend", choices=["claude", "ollama"], default=None,
                         help="defaults to claude if ANTHROPIC_API_KEY is set, else ollama")
    parser.add_argument("--ollama-model", default="qwen2.5:7b",
                         help="model tag for --llm-backend ollama (must already be pulled)")
    parser.add_argument("--ollama-host", default="http://localhost:11434",
                         help="Ollama API address — override to http://host.docker.internal:11434 "
                              "when running the pipeline in Docker against an Ollama server on the host")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    backend = args.llm_backend or ("claude" if os.environ.get("ANTHROPIC_API_KEY") else "ollama")
    llm = (ClaudeLLMClient() if backend == "claude"
           else OllamaLLMClient(model=args.ollama_model, host=args.ollama_host))
    if args.verbose:
        print(f"LLM backend: {backend}" + (f" ({args.ollama_model})" if backend == "ollama" else ""))

    embedder = SentenceTransformerEmbedder()

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
