# Production Implementation Backlog

Companion to [Production Platform Architecture](PROD-PLATFORM-CONFLUENCE.md).
Every item is ticket-ready: scope, dependencies, acceptance criteria, estimate.

**Ordering principle:** correlation and cost control come before dashboards.
A beautiful Grafana board over uncorrelated data is decoration; `trace_id`
propagation over an ugly log line is leverage.

Estimates assume one engineer. `d` = day.

---

## Phase P0 — Instrumentation foundation (~8d)

*Nothing here needs Kubernetes. All of it works in Docker Compose, and all of it
is a prerequisite for everything after.*

### P0-1 · Structured logging
**Est:** 1d · **Deps:** —
- Replace all logging with `structlog` emitting JSON to stdout
- `LogContext` contextvar carrying `run_id`, `tenant_id`, `stage`, `field_key`
- Closed `event` enum in `sfm/obs/events.py`
- Redaction filter: never emit prompt/response bodies or secrets

**AC:** every log line is valid JSON with the full correlation block; a unit test
asserts no log record contains a prompt body.

### P0-2 · OpenTelemetry SDK wiring
**Est:** 2d · **Deps:** P0-1
- OTel tracer + meter providers; OTLP exporter; resource attributes
  (`service.name`, `service.version`, `deployment.environment`)
- Span per stage; span per field in stage 5; span per LLM call
- Inject `trace_id`/`span_id` into every structlog record
- Auto-instrument `httpx`, `asyncpg`, `redis`

**AC:** one run produces one trace with ~45 spans; every log line from that run
carries the same `trace_id`.

### P0-3 · Metrics catalogue
**Est:** 2d · **Deps:** P0-2
- Implement every metric in Architecture §4.1
- `/metrics` endpoint (or OTLP push from workers)
- Recording rules for the derived unit-economics metrics

**AC:** `curl /metrics` shows all counters/histograms with correct labels;
cardinality reviewed — **no `field_key` as a metric label** (it belongs in logs
and traces, not in Prometheus).

### P0-4 · Local observability stack — **DONE, built ahead of P0-3**
**Est:** 2d · **Deps:** ~~P0-3~~ (didn't turn out to be a real dependency — the
stack stands up fine with no app metrics yet)
- ✅ `deploy/observability/docker-compose.yml`: OTel Collector, Prometheus,
  Grafana, Loki, Tempo, Langfuse (+ its Postgres/ClickHouse/Redis/MinIO),
  `langfuse-worker`, LiteLLM — 13 containers, all verified healthy
- ✅ Collector config, Grafana datasources (Prometheus/Loki/Tempo) with
  trace↔log correlation *configured* — no real logs/traces flow through it
  yet since that needs P0-1/P0-2, still open
- ✅ `./scripts/start.sh` / `./scripts/stop.sh` — install, start, stop,
  health-check-wait, print URLs; genuinely reproducible from a clean Docker
  volume, not just working because of leftover state (verified by wiping
  the Grafana volume and confirming everything re-provisions from files)
- **Beyond original scope:** a working `LLM Operations` Grafana dashboard
  (`grafana-clickhouse-datasource` plugin, queries Langfuse's ClickHouse
  store directly) — real token/cost/latency data with zero app
  instrumentation, since P0-1–P0-3 aren't done yet and empty panels help no one
- **Bugs found by actually starting it** (none were visible from reading the
  YAML): missing `prometheus.yml`/`tempo.yaml`/`litellm.config.yaml`/Grafana
  provisioning; invalid `${ENV:-local}` collector syntax; missing
  `CLICKHOUSE_MIGRATION_URL`; ClickHouse needing `CLICKHOUSE_CLUSTER_ENABLED=false`;
  missing S3 region (crashed the process); MinIO bucket never created; and
  the big one — **no `langfuse-worker` service at all**, so traces silently
  never appeared (no error, just permanent "waiting for first trace")

**AC (revised — original AC needs P0-1/P0-2 too):** `./scripts/start.sh` →
Grafana, Langfuse, Prometheus, Loki, Tempo, MinIO all reachable and healthy.
✅ Met. Trace↔log click-through: not yet — no real log/trace data exists to
click between.

### P0-5 · Langfuse integration — **DONE (core), partial on original scope**
**Est:** 1d · **Deps:** P0-4
- ✅ `LangfuseTracedLLMClient` wraps `ClaudeLLMClient`/`OllamaLLMClient`:
  trace = per-table adjudication call, generation = the LLM call, real
  prompt/response/model/token usage recorded
- ✅ `ClaudeLLMClient`/`OllamaLLMClient` now capture real token usage
  (`response.usage` / `prompt_eval_count`+`eval_count`) as `self.last_usage`
- ✅ Auto-enabled by both `run_pipeline.py` (CLI) and `app.py` (Streamlit
  "▶ Run pipeline" button) when `LANGFUSE_PUBLIC_KEY` is set — same
  auto-detect pattern as backend selection, no flag needed. (`app.py`
  initially shipped without this wrapping — a real bug caught by noticing
  Streamlit runs produced zero new Langfuse traces — fixed to mirror
  `run_pipeline.py`'s per-table wrap exactly.)
- ❌ Not done: `prompt_version`/`stage`/`field_key`/`tenant` as separate
  structured tags (generation `name` currently carries table context only,
  e.g. `adjudicate:emp_master`); `langfuse_trace_url` isn't emitted into a
  log line (no structured logging yet — P0-1); prompts haven't been
  migrated into the Langfuse prompt registry, still plain Python functions

**AC (original):** the §6 correlation walkthrough works end to end on a
local run. **Not fully met** — that walkthrough spans Splunk/Tempo/logs too,
which need P0-1/P0-2. What *is* verified end to end: a real pipeline run
produces a real Langfuse trace with real token counts, visible in the UI
and in the Grafana `LLM Operations` dashboard.

---

## Phase P1 — Service-ification (~10d)

### P1-1 · FastAPI service
**Est:** 3d · **Deps:** P0-2
- `POST /v1/runs`, `GET /v1/runs/{id}`, `GET /v1/runs/{id}/mapping`,
  `GET /v1/health`, `GET /v1/ready`
- Idempotency keys on run creation (Redis)
- OpenAPI spec published
**AC:** contract tests green; readiness probe fails when Postgres or Redis is down.

### P1-2 · Postgres persistence
**Est:** 2d · **Deps:** P1-1
- Schema: `runs`, `table_mappings`, `field_mappings`, `review_decisions`,
  `audit_log` (append-only)
- Alembic migrations; row-level security by `tenant_id`
**AC:** a run is fully reconstructible from the database; audit rows are
insert-only (enforced by a trigger, not by convention).

### P1-3 · Redis cache + queue
**Est:** 1d · **Deps:** P1-2
- Replace the disk cache; same content-addressed key; TTL 30d
- Cache hit/miss metrics by layer
**AC:** cold run populates, warm run hits >95%, `sfm_llm_cache_hits_total` moves.

### P1-4 · Temporal workflow
**Est:** 3d · **Deps:** P1-3
- Pipeline as a Temporal workflow; each stage an activity with its own retry policy
- Heartbeats on the long stage-5 fan-out
- Resume from the last completed stage on worker loss
**AC:** kill a worker mid-stage-5; the run completes without re-issuing cached calls.

### P1-5 · LiteLLM gateway
**Est:** 1d · **Deps:** P1-1
- Deploy LiteLLM Proxy; route all traffic through it
- Virtual keys per tenant, per-key budgets, fallback chain
  (Anthropic API → Bedrock)
- Enable semantic caching, measure the incremental hit rate before keeping it
**AC:** revoking a tenant key stops that tenant's calls and nobody else's;
simulated provider 500s trigger failover.

---

## Phase P2 — Enterprise logging & dashboards (~7d)

### P2-1 · Splunk HEC integration
**Est:** 2d · **Deps:** P0-4
- Collector Splunk HEC exporter; TLS; token from Vault
- Indexes `sfm_app` / `sfm_audit` / `sfm_security`; sourcetype `sfm:json`
- Routing rule: `WARN`+ → Splunk, everything → Loki
- Sampling processor: 10% on per-field events
**AC:** events searchable in Splunk within 30s with all fields extracted; measured
daily ingest volume documented and within the agreed budget.

### P2-2 · Splunk saved searches & audit dashboard
**Est:** 1d · **Deps:** P2-1
- The five saved searches from Architecture §7
- Compliance dashboard: who ran what, who approved which mapping
**AC:** an auditor can answer "who approved the `rec_stat` mapping for tenant
Acme on 12 Aug" in under a minute.

### P2-3 · Grafana dashboards as code
**Est:** 3d · **Deps:** P0-3, P2-1
- D1 Service Health, D2 LLM Operations, D3 Mapping Quality, D4 FinOps
- JSON in `deploy/grafana/dashboards/`, provisioned, in git
- Deploy and prompt-version annotations on every timeseries
**AC:** dashboards reproduce from a clean Grafana with no manual clicking.

### P2-4 · Alerting
**Est:** 1d · **Deps:** P2-3
- Every alert rule in Architecture §9 as code
- Alertmanager → PagerDuty (P1/P2) and Slack (P3/P4)
- A runbook page per alert, linked from the annotation
**AC:** each alert fires in a staging drill and its runbook resolves it.

---

## Phase P3 — Quality & governance (~9d)

### P3-1 · Langfuse eval in CI
**Est:** 2d · **Deps:** P0-5
- Gold mapping as a Langfuse dataset
- CI job on any `sfm/prompts/**` change: run the dataset, push scores
- Fail the build on accuracy@1 −2pp or recall@5 < 1.0
**AC:** a deliberately degraded prompt fails the PR with a readable diff.

### P3-2 · Human review UI
**Est:** 3d · **Deps:** P1-2
- Queue of `needs_review` mappings, sorted by confidence
- Accept / reject / correct, with the signal breakdown and runner-up shown
- Decisions written to `review_decisions` + `audit_log`, and pushed to Langfuse
  as scores
**AC:** a reviewer decision is visible in Postgres, the audit index, and Langfuse.

### P3-3 · Secrets & authn/authz
**Est:** 2d · **Deps:** P1-1
- Vault + External Secrets Operator; no secrets in images or env files
- OIDC SSO; roles `viewer`/`operator`/`reviewer`/`admin`
**AC:** no secret in any image layer (verified by Trivy secret scan); RBAC
enforced by an integration test per role.

### P3-4 · Input safety
**Est:** 2d · **Deps:** P1-5
- Presidio scan on ingested schemas — flag PII-revealing column names/comments
- Extend `PromptGuard` with injection detection on schema comments
  (comments are untrusted input and go straight into prompts)
- Cap on schema size and field count per run
**AC:** a schema whose comment contains `ignore previous instructions` is
rejected with a clear error and a security-index log event.

---

## Phase P4 — Platform hardening (~10d)

### P4-1 · Kubernetes + Helm
**Est:** 3d — one chart, per-env values, resource limits, PDBs, non-root distroless images
### P4-2 · ArgoCD GitOps
**Est:** 2d — app-of-apps, sync waves, automated rollback on failed health
### P4-3 · KEDA autoscaling
**Est:** 1d — scale workers on Temporal queue depth; scale-to-zero off-hours
### P4-4 · Supply chain security
**Est:** 2d — Trivy gate on CRITICAL, Syft SBOM, Cosign signing, Kyverno policy
### P4-5 · DR & backup
**Est:** 2d — Postgres PITR, S3 versioning + Object Lock, **rehearsed** restore

---

## Phase P5 — Scale & optimisation (~8d)

### P5-1 · Vector store migration
**Est:** 2d — pgvector → Qdrant if >1M vectors; benchmark recall@K before and after
### P5-2 · Batch & scheduled runs
**Est:** 2d — Temporal cron; bulk schema onboarding; per-tenant concurrency caps
### P5-3 · Cost optimisation
**Est:** 2d — model routing (cheaper model for high-margin retrievals, escalate
only on close calls); prompt-token reduction; cache TTL tuning. **Measure
accuracy before and after — cost work that quietly costs accuracy is a regression.**
### P5-4 · Multi-region
**Est:** 2d — region-pinned deployment for data residency; regional inference endpoints

---

## Summary

| Phase | Focus | Effort | Delivers |
|---|---|---|---|
| P0 | Instrumentation foundation | 8d | Correlated logs, metrics, traces, LLM observability |
| P1 | Service-ification | 10d | API, persistence, durable workflows, LLM gateway |
| P2 | Enterprise logging & dashboards | 7d | Splunk, Grafana, alerting, on-call readiness |
| P3 | Quality & governance | 9d | Eval gates, review UI, secrets, RBAC, input safety |
| P4 | Platform hardening | 10d | k8s, GitOps, autoscaling, supply chain, DR |
| P5 | Scale & optimisation | 8d | Vector scale, batch, cost control, multi-region |
| | **Total** | **~52d** | ~11 weeks for one engineer; ~5 with two |

**Progress:** P0-4 and P0-5 are done (see their entries above for exactly
what that does and doesn't cover). P0-1, P0-2, P0-3, and everything in
P1–P5 are still open.

### If you only do three things

1. **P0-2 — `trace_id` propagation.** Everything else compounds off it.
2. **P0-5 — Langfuse.** LLM systems fail in ways ordinary APM cannot see;
   without prompt-level visibility you are debugging blind.
3. **P3-1 — eval gate in CI.** A prompt is a deploy. Prompts that ship without a
   regression gate will silently degrade quality, and you will find out from a
   customer rather than from a build.
