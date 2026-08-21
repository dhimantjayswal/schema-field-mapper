# Schema Field Mapper — Production Platform Architecture

> **Page type:** Architecture / Platform Design
> **Status:** DRAFT — for review
> **Owner:** Dhimant
> **Audience:** Platform Engineering, SRE, Data Engineering, Security
> **Related:** [Schema Field Mapper — Design Docs] · [Implementation Backlog]

---

## 1. Purpose

The Schema Field Mapper began as a CLI that produces a JSON mapping document. This
page defines what it takes to run that capability as an **enterprise service**:
containerised, observable, governed, cost-controlled, and safe to operate at 3am
by someone who did not build it.

**Scope in:** runtime platform, observability, LLM operations, security,
CI/CD, data stores, cost governance.
**Scope out:** the mapping algorithm itself (covered in the design docs).

### 1.1 What changes from the CLI

| Concern | Prototype | Production |
|---|---|---|
| Invocation | `sfm map` on a laptop | REST API + async workers + scheduled batch |
| Logs | stdout | Structured JSON → collector → Splunk, 90-day retention |
| Metrics | printed summary | Prometheus + Grafana, SLOs, alerting |
| LLM visibility | JSONL trace file | Langfuse traces, per-run cost, prompt versioning, eval history |
| Cache | local disk | Redis with TTL + semantic cache at the gateway |
| Secrets | `.env` | Vault / External Secrets Operator, rotated |
| Failure | traceback | Retries, DLQ, circuit breaker, alert, runbook |
| Cost | "about ten cents" | Budget guardrails, per-tenant chargeback, anomaly alerts |
| Review | a markdown file | Human-in-the-loop UI with audit trail and RBAC |

---

## 2. Target architecture

```
                          ┌───────────────────────────────────────────┐
     Users / CI ────────► │  API Gateway (Kong / AWS ALB + WAF)        │
                          │  SSO · OIDC · rate limit · mTLS            │
                          └────────────────────┬──────────────────────┘
                                               │
                          ┌────────────────────▼──────────────────────┐
                          │  sfm-api (FastAPI)                        │
                          │  POST /runs · GET /runs/{id} · /review    │
                          └────────────────────┬──────────────────────┘
                                               │ enqueue
                          ┌────────────────────▼──────────────────────┐
                          │  Workflow engine (Temporal)               │
                          │  durable 7-stage pipeline · retries       │
                          └────────────────────┬──────────────────────┘
                                               │
              ┌────────────────────────────────┼──────────────────────────────┐
              │                                │                              │
    ┌─────────▼────────┐          ┌────────────▼───────────┐      ┌───────────▼──────────┐
    │ sfm-worker pods  │          │  LLM Gateway (LiteLLM) │      │  Vector store        │
    │ stages 1–7       │─────────►│  keys · fallback ·     │      │  pgvector / Qdrant   │
    │ HPA on queue     │          │  budgets · sem. cache  │      └──────────────────────┘
    └────────┬─────────┘          └────────────┬───────────┘
             │                                 │
             │                        ┌────────▼────────┐
             │                        │ Anthropic /     │
             │                        │ Bedrock / Azure │
             │                        └─────────────────┘
             │
    ┌────────▼─────────────────────────────────────────────────────────────┐
    │  Data plane                                                          │
    │  PostgreSQL (runs, mappings, review decisions, audit)                │
    │  Redis (cache, queue, idempotency keys)                              │
    │  S3 / MinIO (input schemas, output artifacts, versioned)             │
    └──────────────────────────────────────────────────────────────────────┘

    ── Observability plane (cross-cutting) ─────────────────────────────────
    OpenTelemetry SDK in every service
        ├── logs    → OTel Collector → Splunk HEC        (+ Loki for cheap hot tier)
        ├── metrics → Prometheus     → Grafana / Alertmanager
        ├── traces  → Tempo / Jaeger → Grafana
        └── LLM     → Langfuse (traces, tokens, cost, prompts, evals, scores)
```

### 2.1 Design principle: instrument once, fan out

Every service emits **OpenTelemetry only**. The OTel Collector decides where
signals land. This means switching Splunk → Elastic, or Tempo → Jaeger, is a
collector config change, not an application change. Do not write vendor SDKs into
application code — that is the single most expensive observability mistake teams
make, and it is entirely avoidable.

**Exception:** Langfuse. LLM observability needs semantics OTel does not model
natively (prompt version, token split, model, evaluation score, human feedback).
Use the Langfuse SDK directly, wrapped in our own `LLMClient` so it stays
swappable. OTel GenAI semantic conventions are maturing — revisit in 12 months.

---

## 3. Tool selection — the master list

Recommendation column is the default choice. Alternatives are listed because
your org may already have a licence, and "we already pay for it" beats "it is
marginally better" almost every time.

### 3.1 Runtime & orchestration

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| Container runtime | Docker / containerd | Podman | Multi-stage build, distroless base, non-root |
| Orchestration | Kubernetes (EKS/AKS/GKE) | ECS Fargate, Nomad | ECS is fine if you have no k8s platform team |
| Packaging | Helm | Kustomize | One chart, per-env values |
| GitOps deploy | ArgoCD | Flux, Spinnaker | Git as the source of truth for cluster state |
| Autoscaling | HPA + KEDA | — | **KEDA on queue depth**, not CPU — LLM work is IO-bound and CPU tells you nothing |
| Workflow engine | Temporal | Prefect, Dagster, Airflow, Celery | Durable execution matters: a 7-stage pipeline that dies at stage 6 must resume, not restart and re-spend tokens |
| Service mesh | Istio / Linkerd | — | Only if mTLS and traffic policy are org requirements |

### 3.2 Logging (the "Splunk" pillar)

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| App logging lib | `structlog` → JSON | `python-json-logger` | Never log unstructured strings |
| Collection | OTel Collector (DaemonSet) | Fluent Bit, Fluentd, Vector | Vector is excellent if you need heavy transformation |
| Docker-local | `json-file` driver + Promtail | `splunk` log driver | For the compose-based dev stack |
| Primary sink | **Splunk Enterprise / Cloud** via HEC | Elastic (ELK), Datadog Logs, Sumo Logic | HEC over TLS, token in Vault |
| Cheap hot tier | Grafana Loki | — | Loki for 7-day dev/debug, Splunk for 90-day audit — a real cost saver |
| Log→metric | OTel Collector `count_connector` | Splunk saved searches | Derive error-rate metrics at the collector, not in Splunk |

### 3.3 Metrics & dashboards (the "Grafana" pillar)

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| Metrics SDK | OTel Metrics (Python) | `prometheus_client` | |
| Store | Prometheus + Thanos/Mimir | VictoriaMetrics, Datadog | Thanos for >15-day retention and global query |
| Dashboards | **Grafana** | Datadog, Splunk Observability | Dashboards as code — JSON in git, provisioned |
| Container metrics | cAdvisor + kube-state-metrics + node-exporter | — | Standard k8s bundle |
| Alerting | Alertmanager → PagerDuty + Slack | Grafana Alerting, Opsgenie | Alert rules as code, reviewed in PR |
| Synthetic checks | Grafana Synthetic Monitoring / Blackbox exporter | Pingdom | Catch "up but broken" |

### 3.4 Tracing

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| Trace SDK | OpenTelemetry auto + manual spans | — | One trace per mapping run; span per stage; span per field |
| Backend | Grafana Tempo | Jaeger, Datadog APM, Honeycomb | Tempo integrates with Loki/Grafana via trace ID |
| Correlation | `trace_id` in every log line and Langfuse trace | — | **The single highest-value integration on this page** — see §6 |

### 3.5 LLM observability (the "Langfuse" pillar)

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| LLM tracing & cost | **Langfuse (self-hosted)** | Helicone, Arize Phoenix, LangSmith, Braintrust, W&B Weave | Self-host: prompts and schemas are customer data |
| Prompt registry | Langfuse Prompt Management | Git-only (current), PromptLayer | Lets you change a prompt without redeploying — with versioning and rollback |
| Eval / scoring | Langfuse Datasets + Scores | Ragas, DeepEval, Promptfoo, Arize | Wire the existing gold mapping in as a Langfuse dataset |
| Human annotation | Langfuse annotation queues | Label Studio, Argilla | This is the reviewer workflow for low-confidence mappings |
| LLM gateway | **LiteLLM Proxy** | Portkey, Cloudflare AI Gateway, Kong AI Gateway | Multi-provider fallback, per-team virtual keys, budgets, semantic cache |

**Why a gateway even with one provider:** provider outage failover
(Anthropic API → Bedrock), per-team budget enforcement, key rotation without a
redeploy, and a single place to enforce rate limits. It is roughly a day of work
and removes an entire category of incident.

### 3.6 Data stores

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| Operational DB | PostgreSQL 16 (RDS/CloudSQL) | — | Runs, mappings, review decisions, audit log |
| Cache & queue | Redis / ElastiCache | — | Replaces the local disk cache; TTL + eviction policy |
| Object store | S3 / MinIO | Azure Blob, GCS | Versioning on; input schemas and output artifacts immutable |
| Vector store | pgvector | Qdrant, Weaviate, Milvus | Start with pgvector — one fewer system until you exceed ~1M vectors |
| Migrations | Alembic | — | Forward-only, reviewed, run as a Helm pre-upgrade hook |

### 3.7 Security & governance

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| Secrets | HashiCorp Vault + External Secrets Operator | AWS Secrets Manager, Doppler | No secrets in env files or images |
| AuthN/Z | OIDC via Okta / Entra ID / Keycloak | — | RBAC: `viewer` / `operator` / `reviewer` / `admin` |
| PII detection | Microsoft Presidio | AWS Comprehend, Nightfall | Schemas may carry PII-revealing column names and comments |
| Prompt-injection guard | Existing `PromptGuard` + LLM Guard / Rebuff | Lakera Guard | Schema comments are untrusted input — treat them as such |
| Image scanning | Trivy | Grype, Snyk | Block on CRITICAL in CI |
| SBOM & provenance | Syft + Cosign (Sigstore) | — | Signed images, attested builds |
| Policy | OPA Gatekeeper / Kyverno | — | No root, no `:latest`, resource limits required |
| Audit trail | Append-only Postgres table + Splunk index | — | Who ran what, who approved which mapping, immutable |
| Data residency | Region-pinned deployment; Bedrock for in-region inference | — | Ask legal before the first customer schema arrives |

### 3.8 CI/CD & quality

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| CI | GitHub Actions | GitLab CI, Jenkins | |
| CD | ArgoCD (GitOps) | Argo Rollouts for canary | |
| Quality gates | ruff, mypy --strict, pytest ≥85%, import-linter | — | Already defined in the design docs |
| **LLM eval gate** | Promptfoo / Langfuse eval in CI | DeepEval | **A prompt change must fail the build if accuracy@1 or recall@5 regresses** |
| IaC | Terraform + Terragrunt | Pulumi, CDK | |
| IaC scanning | Checkov / tfsec | — | |
| Load testing | k6 | Locust | Model provider latency dominates — test with a stubbed provider too |

### 3.9 FinOps

| Capability | Recommended | Alternatives | Notes |
|---|---|---|---|
| LLM cost attribution | Langfuse + LiteLLM budgets | Helicone | Tag every call: tenant, run, stage, prompt version |
| Infra cost | Kubecost / OpenCost | CloudHealth | |
| Budget alerts | Alertmanager on `sfm_llm_cost_usd_total` | Provider-side budget alerts | Alert at 60/80/100% of monthly budget |
| Unit economics | `cost_per_mapped_field` as a first-class metric | — | The number your director will ask for. Have it on a dashboard. |

---

## 4. What to instrument

### 4.1 Metrics catalogue

Naming follows Prometheus convention: `sfm_<subsystem>_<name>_<unit>`.

**Pipeline (RED)**
| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `sfm_runs_total` | counter | `status`, `tenant`, `source_db` | Throughput |
| `sfm_run_duration_seconds` | histogram | `status` | Latency SLO |
| `sfm_stage_duration_seconds` | histogram | `stage` | Which stage is slow |
| `sfm_stage_failures_total` | counter | `stage`, `error_type` | Error budget |
| `sfm_fields_processed_total` | counter | `source_table` | Volume |
| `sfm_queue_depth` | gauge | `queue` | KEDA scaling input |

**LLM**
| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `sfm_llm_calls_total` | counter | `model`, `stage`, `prompt_version`, `outcome` | Call volume |
| `sfm_llm_tokens_total` | counter | `model`, `direction` (`input`/`output`), `stage` | **Token accounting** |
| `sfm_llm_cost_usd_total` | counter | `model`, `tenant`, `stage` | Spend |
| `sfm_llm_latency_seconds` | histogram | `model`, `stage` | p50/p95/p99 |
| `sfm_llm_cache_hits_total` | counter | `layer` (`redis`/`semantic`) | Cache effectiveness |
| `sfm_llm_retries_total` | counter | `reason` (`429`/`5xx`/`timeout`/`parse`) | Provider health |
| `sfm_llm_parse_failures_total` | counter | `prompt_version` | Prompt regression signal |

**Quality**
| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `sfm_mapping_confidence` | histogram | `source_table` | Confidence distribution |
| `sfm_coverage_ratio` | gauge | `run_id` | Fields accounted for / total |
| `sfm_unmapped_fields_total` | counter | `reason` | Watch for drift |
| `sfm_needs_review_total` | counter | `reason` | Reviewer workload |
| `sfm_type_transform_corrections_total` | counter | `prompt_version` | How often the model got types wrong |
| `sfm_eval_accuracy_at_1` | gauge | `prompt_version` | Pushed from the eval job |
| `sfm_eval_recall_at_k` | gauge | `prompt_version` | **Hard gate metric** |
| `sfm_eval_ece` | gauge | `prompt_version` | Calibration drift |

**Derived unit economics:** `sfm_llm_cost_usd_total / sfm_fields_processed_total`
— a recording rule, not an application metric.

### 4.2 Log event schema

One JSON object per line. Every line carries the correlation block.

```json
{
  "timestamp": "2026-08-21T14:48:03.221Z",
  "level": "INFO",
  "service": "sfm-worker",
  "version": "1.4.2",
  "env": "prod",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "run_id": "run_01J9X...",
  "tenant_id": "acme",
  "stage": "adjudicate",
  "field_key": "emp_master.hire_dt",
  "event": "llm_call_completed",
  "prompt_version": "adjudicate.v2",
  "model": "claude-sonnet-4-6",
  "input_tokens": 712,
  "output_tokens": 143,
  "latency_ms": 1840,
  "cache_hit": false,
  "cost_usd": 0.00327,
  "outcome": "success",
  "langfuse_trace_url": "https://langfuse.internal/trace/..."
}
```

**Rules:**
1. `trace_id` and `run_id` on **every** line, no exceptions.
2. Never log prompt or response bodies to Splunk — they go to Langfuse, which has
   the right access controls and retention. Splunk gets the metadata and the
   Langfuse link. This keeps Splunk costs sane and keeps customer schema content
   out of a broadly-readable index.
3. `event` is a closed enum, defined in code. Splunk searches key off `event`,
   not off message text. Free-text search over log messages is a habit that
   breaks the first time someone rewords a log line.
4. Log levels: `ERROR` = a human must act. `WARN` = degraded but handled
   (retry, downgrade, escalation). `INFO` = state transitions. `DEBUG` = off in prod.

### 4.3 Trace structure

```
Trace: mapping_run (run_id, tenant)
├── span: s1_ingest
├── span: s2_enrich
├── span: s3_entity_align
│   └── span: llm_call (entity_align.v1)          → linked to Langfuse generation
├── span: s4_retrieve
├── span: s5_adjudicate
│   ├── span: adjudicate_field[emp_master.emp_id] → Langfuse generation
│   ├── span: adjudicate_field[emp_master.dob]    → Langfuse generation
│   └── ... (34 spans, concurrent)
├── span: s6_verify
├── span: s7_assemble
└── span: validate_output
```

---

## 5. Grafana dashboards

Dashboards as code: JSON in `deploy/grafana/dashboards/`, provisioned by the
Grafana operator. Four dashboards, each with one audience.

### D1 — Service Health (audience: on-call)
- Run success rate (stat, red under SLO)
- Run duration p50/p95/p99 (timeseries)
- Queue depth and worker replica count (timeseries, overlaid)
- Error rate by stage (bar gauge)
- Pod restarts, OOMKills, CPU/memory saturation
- Active alerts panel

### D2 — LLM Operations (audience: the team) ← *the "Langfuse-like" view*
- Calls/min by model and stage
- **Input vs output tokens over time (stacked)**
- Token distribution per call (heatmap) — spot prompt bloat immediately
- Cost/hour and cumulative month-to-date vs budget line
- Cache hit rate by layer (stat) — target >60% steady state
- Provider latency p95 by model
- Retry rate by reason (timeseries) — provider degradation early warning
- Parse-failure rate by prompt version — **spikes here mean a bad prompt deploy**
- Deep-link panel to Langfuse filtered by `run_id`

### D3 — Mapping Quality (audience: data stewards, product)
- Confidence histogram per run
- Coverage ratio (gauge, must be 1.0)
- Unmapped fields by reason (pie)
- Needs-review queue depth and age (the reviewer SLA)
- accuracy@1 / recall@5 / ECE over time, annotated with prompt-version deploys
- Type-transform correction rate

### D4 — FinOps (audience: engineering management)
- Cost per run, cost per mapped field (the headline numbers)
- Spend by tenant (chargeback)
- Spend by stage — shows where the money actually goes
- Cache savings (counterfactual cost avoided)
- Infra vs LLM cost split
- Monthly projection vs budget

**Dashboard hygiene:** every panel answers a question someone actually asks. A
panel nobody has looked at in 90 days gets deleted. Annotate deploys and prompt
version changes onto every timeseries — most "why did this change?" questions are
answered by a vertical line.

---

## 6. Correlation — the integration that makes this worth doing

The pillars are only valuable when a single identifier walks across all of them.

**The 3am path, end to end:**

1. PagerDuty fires: `SFMHighParseFailureRate`.
2. Alert links to **Grafana D2**, which shows the spike started at 14:20 and is
   isolated to `prompt_version=adjudicate.v3`.
3. Panel links to **Splunk**: `index=sfm event=llm_parse_failed prompt_version=adjudicate.v3`
   → 41 events, all on `stage=adjudicate`, one `run_id` dominant.
4. Splunk event carries `trace_id` → **Tempo** shows the full run, with the
   failing field spans in red.
5. The failing span carries `langfuse_trace_url` → **Langfuse** shows the exact
   prompt, the exact malformed response, and the diff against `adjudicate.v2`.
6. Rollback the prompt in the Langfuse prompt registry — no redeploy.
7. Total time to resolution: minutes, not hours.

Implement `trace_id` propagation **first** (P0). Without it you have four
disconnected tools and four separate investigations.

---

## 7. Splunk configuration

| Item | Value |
|---|---|
| Ingest | HTTP Event Collector (HEC), TLS, token in Vault, rotated quarterly |
| Index | `sfm_app` (90d), `sfm_audit` (7y, immutable), `sfm_security` (1y) |
| Sourcetype | `sfm:json` — `INDEXED_EXTRACTIONS = json` |
| Timestamp | `timestamp` field, UTC, strict ISO 8601 |
| CIM | Map to Application State and Change datamodels for enterprise dashboards |
| Volume control | `WARN`+ to Splunk; full `INFO` to Loki. Sample high-cardinality per-field events at 10% |

**Saved searches to create**
- `SFM — Failed runs, last 24h` (grouped by `error_type`)
- `SFM — LLM cost by tenant, last 7d`
- `SFM — Prompt parse failures by version`
- `SFM — Audit: mapping approvals` (who approved what, for compliance)
- `SFM — Anomalous token usage` (input tokens > 2× 7-day baseline → prompt bloat or injection)

**Cost warning:** naive per-field logging at enterprise scale will dominate your
Splunk bill. The Loki hot tier + Splunk warm tier split in §3.2 is not premature
optimisation; it is the difference between a $2k and a $30k monthly line item.

---

## 8. Langfuse configuration

**Deployment:** self-hosted via Helm — Langfuse server, Postgres, ClickHouse,
Redis, S3-compatible blob store. Do not use the cloud offering for customer
schema content without a signed DPA and a legal review.

**Mapping our domain onto the Langfuse model**

| Langfuse concept | Our object |
|---|---|
| Trace | One mapping run (`run_id`) |
| Span | One pipeline stage |
| Generation | One LLM call (adjudication, entity align, verify) |
| Session | A tenant's migration project across runs |
| Prompt | `adjudicate.v2` etc., version-managed and rollback-able |
| Dataset | `gold.mapping.json` — 34 items with expected outputs |
| Score | `accuracy@1`, `confidence_calibration`, plus human review verdicts |
| User feedback | Reviewer accept / reject / correct on a mapping |

**Key wins this unlocks**
1. **Prompt rollback without a deploy** — the fastest possible mitigation for a
   bad prompt.
2. **Regression runs on every prompt PR** — the gold dataset runs automatically;
   accuracy regression blocks the merge.
3. **Reviewer corrections become training data** — every human correction is a
   labelled example; feed the best ones back as few-shot examples.
4. **Token and cost attribution for free** — per trace, per generation, per user.

---

## 9. Alerting

| Alert | Condition | Severity | Action |
|---|---|---|---|
| `SFMRunFailureRateHigh` | >5% failures over 15m | P2 | Page on-call |
| `SFMQueueBacklog` | depth >100 for 10m | P3 | Check KEDA scaling |
| `SFMLLMProviderErrors` | 429/5xx >10% over 5m | P2 | Gateway failover to secondary provider |
| `SFMParseFailureSpike` | >3× 7-day baseline | P2 | Suspect prompt deploy → check version → roll back |
| `SFMCostBudget80` | MTD spend ≥80% of budget | P3 | Notify Slack; review before it hits 100% |
| `SFMCostAnomaly` | Hourly spend >3σ above baseline | P2 | Possible runaway loop or injection |
| `SFMCoverageBelowOne` | any run with coverage <1.0 | P2 | Correctness gate breached — investigate before shipping the artifact |
| `SFMEvalRegression` | accuracy@1 drops >2pp | P2 | Block promotion, roll back prompt |
| `SFMReviewQueueStale` | items >48h old | P4 | Nudge the data steward |

**Alert discipline:** every alert must have a runbook link and a documented human
action. An alert that fires and gets acknowledged with no action taken is a
paging-fatigue generator and should be deleted or converted to a dashboard panel.

### 9.1 SLOs

| SLO | Target | Window |
|---|---|---|
| Run success rate | 99.0% | 30d rolling |
| Run latency (100 fields) | p95 < 180s | 30d |
| API availability | 99.9% | 30d |
| Mapping accuracy@1 | ≥ 94% | per release |
| Coverage | 100% | every run (hard gate) |

Error budget policy: burning >50% in a week freezes feature work until
reliability is restored. Write this down before you need it.

---

## 10. Non-functional requirements

| NFR | Target |
|---|---|
| Throughput | 50 concurrent runs; 10k fields/hour |
| Availability | 99.9% API |
| RTO / RPO | 1h / 15min (Postgres PITR) |
| Data retention | Artifacts 7y (S3 versioned + Object Lock), app logs 90d, traces 30d |
| Encryption | TLS 1.3 in transit; KMS at rest; envelope encryption for schema content |
| Multi-tenancy | Row-level security in Postgres; per-tenant LLM budgets and virtual keys |
| Compliance | SOC 2 controls; GDPR — schema content may reveal PII structure |
| DR | Multi-AZ; documented and **rehearsed** cross-region restore |

---

## 11. Decisions register

| # | Decision | Rationale | Status |
|---|---|---|---|
| P-001 | OTel as the sole instrumentation API | Vendor portability; one code path | Proposed |
| P-002 | Langfuse SDK direct (not via OTel) | GenAI semantics not yet stable in OTel | Proposed |
| P-003 | Temporal over Celery | Durable resume — a stage-6 failure must not re-spend tokens | Proposed |
| P-004 | LiteLLM gateway even with one provider | Failover, budgets, key rotation, semantic cache | Proposed |
| P-005 | Loki hot + Splunk warm | Splunk-only ingest of per-field events is cost-prohibitive | Proposed |
| P-006 | Self-hosted Langfuse | Prompts and schemas are customer data | Proposed |
| P-007 | pgvector before a dedicated vector DB | One fewer system until ~1M vectors | Proposed |
| P-008 | KEDA on queue depth, not CPU | Workload is IO-bound on provider latency | Proposed |

## 12. Open questions

1. Is there an existing enterprise Splunk contract, and who owns index creation?
2. Which LLM provider is approved by security — direct API, Bedrock, or Azure?
3. Data residency requirements for customer schema content?
4. Who staffs the mapping review queue, and what is their SLA?
5. Chargeback model — per tenant, per run, or absorbed centrally?
6. Existing k8s platform, or does this need its own cluster?

---

## 13. Appendix — Confluence import

This page is authored in Markdown so it lives in git next to the code.

- **Manual:** Confluence → Create → `⋯` → *Insert Markdown* (or paste; Confluence
  Cloud converts most Markdown on paste). Tables and code blocks survive; the
  ASCII diagrams should be moved into a `code` macro or redrawn in draw.io.
- **Automated:** [`markdown-confluence`](https://github.com/markdown-confluence/markdown-confluence)
  or `mark` (`github.com/kovetskiy/mark`) in CI, so the page is regenerated from
  `main` on every merge and never drifts from reality.
- **Recommended:** the automated path. A Confluence page that is hand-maintained
  alongside a repo is a page that will be wrong within two sprints.
