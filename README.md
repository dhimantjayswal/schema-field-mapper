# Schema Field Mapper

AI pipeline that maps every field in the `legacy_hrm` MySQL schema to its
semantic equivalent in the `people_platform` MongoDB schema, and emits a
single JSON mapping document. Built for the IBM AI/LLM Engineer interview
assignment (`InterviewAssignment.docx`).

## Why this isn't one big prompt

The assignment's explicit constraint: *"You cannot pass both schemas to an
LLM in a single prompt and receive a finished mapping."* This pipeline
retrieves a short candidate list per source field with local embeddings
first, then asks Claude to adjudicate one source table at a time against
only its own candidates — never both full schemas in one call. Full
reasoning in `WRITEUP.md`.

## UI

```bash
streamlit run app.py
```

A dashboard, not a second implementation — it imports `pipeline/` directly
and calls the same stages `run_pipeline.py` does. Watch the pipeline map
each table live from the sidebar (`▶ Run pipeline`), or just browse the
last `output/mapping.json`: per-table results with confidence bars,
unmapped-field warnings, and the gold-mapping eval scorecard, all in one
page instead of raw JSON + a separate `evaluate_mapping.py` call.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.9+.

## Run

Two LLM backends for Stage 4/7 — pick whichever you have:

**No API key?** Run a local model via [Ollama](https://ollama.com):
```bash
ollama pull qwen2.5:7b   # or any model you already have
python run_pipeline.py --verbose --llm-backend ollama --ollama-model qwen2.5:7b
```
This is auto-selected by default when `ANTHROPIC_API_KEY` isn't set — `python run_pipeline.py --verbose` alone is enough if you've already got Ollama running.

**Have a Claude API key?**
```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY
python run_pipeline.py --verbose
```

Writes `output/mapping.json`. Flags:

- `--top-k` (default 5) — candidates retrieved per source field
- `--confidence-threshold` (default 0.7) — fields below this get a Stage 7 re-ask
- `--llm-backend {claude,ollama}` — defaults to claude if `ANTHROPIC_API_KEY` is set, else ollama
- `--ollama-model` (default `qwen2.5:7b`) — any locally-pulled Ollama model tag
- `--verbose` — per-table summary as it runs

## Real databases (Docker)

The assignment frames this as "two database schemas from separate
systems" — `docker-compose.yml` makes that literal: real MySQL
(`legacy_hrm`) and MongoDB (`people_platform`) containers, seeded from the
*same* schema data the pipeline reads (`scripts/generate_db_init.py`
generates the seed scripts from `data/source_schema.py` /
`data/dest_schema.py`, so they can't silently drift out of sync).

```bash
docker compose up -d mysql mongo   # start the two real databases
docker compose build pipeline      # build the pipeline image (bakes in the embedding model)
docker compose run --rm pipeline   # run it — reaches Ollama on the host via host.docker.internal
docker compose down -v             # stop and wipe the seeded data
```

Inspect what got seeded:

```bash
docker exec -it $(docker compose ps -q mysql) mysql -uroot -proot -e "USE legacy_hrm; SHOW TABLES; DESCRIBE emp_master;"
docker exec -it $(docker compose ps -q mongo) mongosh people_platform --eval "db.getCollectionNames()"
```

The MongoDB collections carry a real `$jsonSchema` validator reconstructed
from the flattened dot-paths back into their nested document shape — try
inserting a document with `isRemote: "not-a-bool"` and MongoDB itself
rejects it.

The pipeline still maps from `data/source_schema.py` / `data/dest_schema.py`
directly, not by introspecting the live containers — that's a separate,
larger feature (live schema introspection) this doesn't attempt.

With a Claude key instead of Ollama: `docker compose run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY pipeline --llm-backend claude`.

## Test

```bash
pytest
```

The test suite is fully cold — no network calls, no `ANTHROPIC_API_KEY`
required, no model download. `tests/fakes.py` provides a deterministic
bag-of-words embedder and a fake LLM client that exercise the real pipeline
wiring (Stages 0-7) against fixed, inspectable logic.

Every function in `pipeline/` also has a docstring with a runnable
`Example:` (verified via `doctest`, not just written and hoped-for):

```bash
python -c "
import doctest, importlib
mods = ['pipeline.names', 'pipeline.lexicon', 'pipeline.roles', 'pipeline.parse_schema',
         'pipeline.align_tables', 'pipeline.embed_candidates', 'pipeline.llm_client',
         'pipeline.prompts', 'pipeline.map_fields', 'pipeline.validate', 'pipeline.reask',
         'pipeline.assemble', 'pipeline.evaluate', 'tests.fakes']
for name in mods:
    print(name, doctest.testmod(importlib.import_module(name)))
"
```

## Evaluate

```bash
python evaluate_mapping.py
```

Scores `output/mapping.json` against `data/gold_mapping.py` — a
hand-curated ground truth for all 34 source fields, written independently
of the pipeline so the check isn't circular. Reports `accuracy@1`,
`coverage`, `path_validity` (no hallucinated destination paths), sliced by
difficulty. See `WRITEUP.md` for a real result and the bug it caught.

## Production readiness (next phase)

Everything above is a working prototype. `docs/production/PROD-PLATFORM-CONFLUENCE.md`
is the architecture doc for running this as an enterprise service —
structured logging → Splunk, Prometheus/Grafana metrics, Langfuse-style
LLM observability (tokens, cost, prompt versioning), a FastAPI + Temporal
service layer, and the security/CI/FinOps tooling around it.
`docs/production/PROD-IMPLEMENTATION-BACKLOG.md` breaks that into 24
ticket-ready items across 6 dependency-ordered phases (~52 engineer-days),
each with acceptance criteria — start at Phase P0, `trace_id` propagation
is the one thing everything else compounds off of.

`deploy/observability/` has the local dev stack for Phase P0 (OTel
Collector, Prometheus, Grafana, Loki, Tempo, Langfuse, LiteLLM) — not yet
wired to the application code; that's P0-1 through P0-5 in the backlog.

## Pipeline stages

| Stage | Module | LLM call? |
| :-- | :-- | :-- |
| 0 — Parse & normalize | `pipeline/parse_schema.py` (roles from `pipeline/roles.py`) | no |
| 1 — Table/collection alignment | `pipeline/align_tables.py` | no — name/field-overlap heuristic, see `WRITEUP.md` |
| 3 — Candidate retrieval | `pipeline/embed_candidates.py` (name-overlap via `pipeline/lexicon.py`) | no — local sentence-transformers |
| 4 — Field adjudication | `pipeline/map_fields.py`, `pipeline/prompts.py`, `pipeline/llm_client.py` | yes, one call per source table |
| 5 — Validation, conflicts & completeness | `pipeline/validate.py` | no |
| 7 — Low-confidence re-ask | `pipeline/reask.py` | yes, only for fields below threshold |
| 6 — Assembly | `pipeline/assemble.py` | no |

Stage 2 (flattening destination fields to dot-paths) is done once, by hand,
directly in `data/dest_schema.py` rather than as runtime code — the
destination shape is static and small enough that a generic flattener
would be solving a problem this input doesn't have.

## Status

`output/mapping.json` in this repo was generated by an actual run of
`run_pipeline.py` against the local Ollama backend (`qwen2.5:7b`) — real
pipeline output, not hand-written. It currently scores 97.06% accuracy@1
against `data/gold_mapping.py` (`python evaluate_mapping.py`; 33/34, the
one miss being `dept_stat` — a genuinely hard lossy-enum case the pipeline
correctly declines to guess on rather than a wrong answer it's confident
about). Both LLM backends are pinned to `temperature=0`: two runs of the
same input now produce byte-identical output apart from `generated_at`.
See `WRITEUP.md` for the real bugs this build found and fixed along the
way (a duplicate-destination collision on `dob`/`created_ts`, and the
non-determinism itself). Re-run it yourself before submitting if you want
a fresh copy or want to try it against Claude.
