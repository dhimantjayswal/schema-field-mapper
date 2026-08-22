"""Streamlit dashboard for the Schema Field Mapper.

Two things this gives you that the CLI doesn't: watching the pipeline map
each table live as it runs (Stage 4/7 LLM calls are the slow part — this
updates the page after each table completes rather than only at the end),
and a browsable view of `output/mapping.json` plus the gold-mapping eval
score, instead of reading raw JSON.

Reuses the real pipeline modules directly (no subprocess, no duplicated
logic) — this is a view onto `pipeline/`, not a second implementation.

Run:
    streamlit run app.py
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from data.gold_mapping import GOLD_MAPPING
from pipeline.align_tables import align_tables
from pipeline.assemble import assemble
from pipeline.embed_candidates import SentenceTransformerEmbedder
from pipeline.evaluate import score_mapping
from pipeline.llm_client import ClaudeLLMClient, LangfuseTracedLLMClient, OllamaLLMClient
from pipeline.map_fields import map_table
from pipeline.reask import reask_low_confidence
from pipeline.validate import validate_table_mapping

load_dotenv()

OUTPUT_PATH = Path(__file__).parent / "output" / "mapping.json"

st.set_page_config(page_title="Schema Field Mapper", layout="wide")
st.title("Schema Field Mapper")
st.caption("legacy_hrm (MySQL) → people_platform (MongoDB)")

with st.sidebar:
    st.header("Run pipeline")
    backend = st.selectbox("LLM backend", ["ollama", "claude"])
    ollama_model = st.text_input("Ollama model", "qwen2.5:7b") if backend == "ollama" else None
    top_k = st.slider("Candidates per field (top-k)", 1, 10, 5)
    threshold = st.slider("Re-ask confidence threshold", 0.0, 1.0, 0.7)
    run_clicked = st.button("▶ Run pipeline", type="primary", use_container_width=True)

if run_clicked:
    try:
        llm = ClaudeLLMClient() if backend == "claude" else OllamaLLMClient(model=ollama_model)
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    embedder = SentenceTransformerEmbedder()
    alignments = align_tables()
    progress_bar = st.progress(0.0)
    live = st.container()

    # Auto-traces to Langfuse (deploy/observability) when its keys are set,
    # same auto-detect-from-environment pattern as run_pipeline.py.
    langfuse_enabled = bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))
    model_name = "claude-sonnet-4-5" if backend == "claude" else ollama_model

    tables = []
    for i, alignment in enumerate(alignments):
        status = live.status(
            f"Mapping **{alignment['source_table']}** → **{alignment['destination_collection']}**...",
            expanded=True,
        )
        table_llm = (
            LangfuseTracedLLMClient(llm, name=f"adjudicate:{alignment['source_table']}", model=model_name)
            if langfuse_enabled else llm
        )
        try:
            raw = map_table(
                alignment["source_table"], alignment["destination_collection"],
                table_llm, embedder, top_k=top_k,
            )
            table = validate_table_mapping(raw, alignment["confidence"], alignment["reasoning"])
            table = reask_low_confidence(table, table_llm, threshold=threshold)
        except Exception as exc:
            status.update(label=f"Failed on {alignment['source_table']}: {exc}", state="error")
            st.stop()
        tables.append(table)
        status.update(
            label=(
                f"{table.source_table} → {table.destination_collection}: "
                f"{len(table.field_mappings)} mapped, {len(table.unmapped_source_fields)} unmapped "
                f"(table confidence {table.confidence:.2f})"
            ),
            state="complete",
        )
        progress_bar.progress((i + 1) / len(alignments))

    document = assemble(tables)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(document, indent=2))
    st.success(f"Wrote {OUTPUT_PATH}")

if not OUTPUT_PATH.exists():
    st.info("No output/mapping.json yet — run the pipeline from the sidebar, "
             "or generate one with `python run_pipeline.py` first.")
    st.stop()

document = json.loads(OUTPUT_PATH.read_text())

st.header("Results")
total_mapped = sum(len(t["field_mappings"]) for t in document["tables"])
total_unmapped = sum(len(t["unmapped_source_fields"]) for t in document["tables"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tables", len(document["tables"]))
c2.metric("Fields mapped", total_mapped)
c3.metric("Fields unmapped", total_unmapped)
c4.metric("Generated at", document["generated_at"][:19].replace("T", " "))

for table in document["tables"]:
    header = (
        f"{table['source_table']} → {table['destination_collection']}"
        f"  (table confidence {table['confidence']:.2f})"
    )
    with st.expander(header, expanded=True):
        st.caption(table["reasoning"])
        if table["field_mappings"]:
            df = pd.DataFrame(table["field_mappings"])[
                ["source_field", "destination_field", "type_transform", "confidence", "reasoning", "notes"]
            ]
            st.dataframe(
                df,
                column_config={
                    "confidence": st.column_config.ProgressColumn(
                        "confidence", min_value=0.0, max_value=1.0, format="%.2f",
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )
        if table["unmapped_source_fields"]:
            st.warning("Unmapped source fields: " + ", ".join(table["unmapped_source_fields"]))
        if table["unmapped_destination_fields"]:
            st.info("Unmapped destination fields (no source claims them): "
                     + ", ".join(table["unmapped_destination_fields"]))

st.header("Evaluation vs. gold mapping")
result = score_mapping(document, GOLD_MAPPING)
c1, c2, c3 = st.columns(3)
c1.metric("Accuracy@1", f"{result['accuracy_at_1']:.1%}")
c2.metric("Coverage", f"{result['coverage']:.1%}")
c3.metric("Path validity", f"{result['path_validity']:.1%}")

st.dataframe(
    pd.DataFrame(result["by_difficulty"]).T.rename_axis("difficulty").reset_index(),
    use_container_width=True,
    hide_index=True,
)

if result["misses"]:
    st.subheader("Misses")
    st.dataframe(pd.DataFrame(result["misses"]), use_container_width=True, hide_index=True)
if result["invalid_paths"]:
    st.error("Hallucinated destination paths: " + ", ".join(result["invalid_paths"]))

with st.expander("Raw mapping.json"):
    st.json(document)
