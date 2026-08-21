# Write-up: Prompt Structure & Design Decisions

## The core constraint

The assignment forbids passing both schemas to an LLM in one prompt and
expecting a finished mapping back. That's not a formatting rule — it rules
out the naive approach (concatenate both schemas, ask for JSON) for three
concrete reasons: no retrieval discipline (search, reasoning, and
formatting all happen in one ungoverned pass), no programmatic way to
verify completeness, and it doesn't scale past toy-sized schemas.

## Pipeline shape

1. **Parse & normalize** (`parse_schema.py`) — both schemas are hand-
   transcribed into canonical Python records once, rather than re-parsed
   from the docx's pseudo-JSON at runtime. The docx text isn't valid JSON
   (MySQL-style `TYPE CONSTRAINT -- comment` on one line, no consistent
   delimiters) — writing a bespoke parser for a one-time, ~74-field input
   that never changes would be solving a problem this task doesn't have.
2. **Table/collection alignment** — a name + field-vocabulary overlap
   heuristic, not an LLM call. At 3-vs-3 with near-identical names
   (`emp_master`↔`employees`, `dept_info`↔`departments`,
   `locations`↔`locations`) an LLM call would add cost and a second point
   of failure for a decision a dozen lines of string comparison make
   correctly and deterministically.
3. **Candidate retrieval (RAG)** — every destination field, scoped to the
   collection Stage 1 already matched, gets embedded locally
   (`sentence-transformers`, `all-MiniLM-L6-v2` — no second API key, no
   network dependency at inference time beyond the one-time model
   download). Every source field in the table being processed gets
   embedded the same way, and the top-k candidates by cosine similarity go
   forward. **This is the mechanism that satisfies the constraint** — the
   LLM that actually reasons about mappings never sees the raw destination
   schema, only a pre-filtered shortlist per field.
4. **Per-table adjudication (the only "real" LLM step)** — one Claude call
   per source table (3 calls total here), forced into structured JSON via
   tool-use, given that table's fields plus each field's retrieved
   candidates — never the sibling tables, never the full destination dump.
   The prompt explicitly instructs the model to omit a field into
   `unmapped_source_fields` rather than force a low-quality match when no
   candidate is genuinely right.
5. **Validation & completeness (no LLM)** — every response is checked
   against a Pydantic model of the exact target shape, and
   `unmapped_source_fields` / `unmapped_destination_fields` are computed by
   set difference against the ground-truth field lists from Stage 0 — in
   code, not trusted to the model's memory across a ~19-field batch.
6. **Low-confidence re-ask** — any field mapping below a confidence
   threshold gets a second, differently-framed single-field call. Expected
   to fire rarely given how close these two schemas are semantically; it
   exists for the genuinely ambiguous cases (see "Hard fields" below), not
   as a blanket accuracy pass.
7. **Assembly (no LLM)** — pure code, merges the three validated per-table
   results into the final `mapping_version` / `source` / `destination` /
   `generated_at` / `tables[]` document.

## Confidence

Each field's final confidence is meant to blend two signals that fail
independently: embedding cosine similarity (objective, but blind to
type-transform nuance) and the LLM's own self-reported confidence
(understands the transform, but self-reports run optimistic). The current
implementation uses the LLM's self-reported confidence directly; blending
in the embedding similarity score is a documented next step once real
output is available to tune weights against, rather than guessed once and
left alone.

## Hard fields worth calling out

- `emp_id` (`INT` PK) → `_id` (`ObjectId`) — not a type cast, an ID-
  generation strategy. `notes` is expected to flag this rather than treat
  it as trivial.
- `mgr_emp_id` / `dept_head_id` — FKs that become `ObjectId` refs *into a
  collection whose own primary keys are also being regenerated* by this
  same migration — the mapping has to be aware the referenced IDs move too.
- `rec_stat` (`CHAR(1)`) → `employment.status` (string enum) — needs an
  explicit `A→active, I→inactive, T→terminated` lookup in `notes`, not
  just a reasoning sentence describing that a lookup exists.

## Local model support (Ollama)

The LLM client sits behind a `Protocol` (`LLMClient.map_fields`), so Stage
4/7 can run against either Claude (the primary design target — real
tool-forced structured output) or a local Ollama model, with the same JSON
schema enforced both ways (Ollama's `format` field accepts a JSON schema
and constrains generation to match it). `run_pipeline.py` auto-selects
Ollama when `ANTHROPIC_API_KEY` isn't set, so the pipeline is fully
runnable end-to-end with no paid API access — relevant since this
environment doesn't have Gen AI API credits. `output/mapping.json` in this
repo was generated this way, against `qwen2.5:7b`.

Running it against real data this way surfaced a genuine retrieval bug:
`is_remote` → `employment.isRemote` is a near-exact name match, but
MiniLM's embedding of the full `description` string (`"emp_master.is_remote
— TINYINT(1) — 0 or 1"`) ranked it 18th of 25 destination candidates
(score 0.058) — the type/comment tokens drowned out the field-name signal,
so the LLM never even saw the correct field as an option and picked `_id`
instead. Fixed by blending cosine similarity with a literal name-overlap
score (Jaccard over `snake_case`/`camelCase`-tokenized field names) in
`top_k_candidates` — `employment.isRemote` now ranks first. This is
exactly the kind of thing "test it against the real data, not just fakes"
is for; the cold test suite's fake embedder didn't catch it because its
bag-of-words tokenizer happened to weight the name tokens correctly by
construction.

Two fields — `dept_stat`→`isActive` and `tz_cd`→`timezone` — are still
left unmapped by `qwen2.5:7b` even though `timezone` is embedding-retrieved
as the top candidate for `tz_cd` (0.665 cosine, no help from name-overlap
since "tz" isn't a token-level match for "timezone"). That's the smaller
local model declining to map fields it's not confident about, which is the
pipeline behaving as designed (Stage 4's prompt explicitly says omit
rather than force a low-quality match) — not a bug. Worth re-running
against Claude to see whether a stronger model closes that last gap.

## What's deliberately out of scope

No vector database — brute-force cosine similarity over ~30 destination-
field embeddings is instant at this scale; adding one would be
infrastructure for a problem three tables don't have. No LLM call for
table alignment, for the same reason. Both are documented simplifications,
not oversights.

## Testing strategy

The test suite (`pytest`) is fully cold: `tests/fakes.py` swaps in a
deterministic bag-of-words embedder and a fake LLM client that reads the
candidate list back out of the real prompt text, so the actual pipeline
wiring (Stages 0-7) is exercised end to end with no network call, no
`ANTHROPIC_API_KEY`, and no model download. The completeness check
(`test_pipeline_end_to_end.py::test_every_source_field_accounted_for`) is
the one that matters most for this assignment's explicit requirement that
every field across all three source tables be covered.
