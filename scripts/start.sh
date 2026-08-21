#!/usr/bin/env bash
# Installs deps, starts every service this project uses, and prints where to
# find each one. Idempotent — safe to re-run: already-running containers are
# left alone (`docker compose up -d`), and the venv/pip install are cheap
# no-ops when nothing changed.
#
# Starts:
#   - Python venv + requirements.txt
#   - MySQL (legacy_hrm) + MongoDB (people_platform)          [docker-compose.yml]
#   - Grafana, Langfuse (+worker), Prometheus, Loki, Tempo,
#     OTel Collector, LiteLLM, ClickHouse, MinIO, Postgres,
#     Redis                                          [deploy/observability/docker-compose.yml]
#
# Usage: ./scripts/start.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon isn't running — start Docker Desktop and try again." >&2
  exit 1
fi

echo "== Python environment =="
if [ ! -d .venv ]; then
  echo "  Creating .venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
echo "  Ready: $ROOT/.venv"

echo
echo "== .env =="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  Created .env from .env.example — fill in ANTHROPIC_API_KEY and/or LANGFUSE_* keys when ready."
else
  echo "  Already exists, left as-is."
fi

echo
echo "== App databases (MySQL, MongoDB) =="
docker compose up -d mysql mongo

echo
echo "== Observability stack (Grafana, Langfuse, Prometheus, Loki, Tempo, LiteLLM) =="
(cd deploy/observability && docker compose up -d)

echo
echo "== Waiting for health checks =="
wait_healthy() {
  # $1 = service name, $2 = directory containing its docker-compose.yml
  local service="$1" dir="$2" timeout=90 waited=0 cid
  cid=$(cd "$dir" && docker compose ps -q "$service" 2>/dev/null || true)
  if [ -z "$cid" ]; then
    echo "  WARNING: $service — container not found (check docker compose logs)"
    return 0
  fi
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null)" = "healthy" ]; do
    if [ "$waited" -ge "$timeout" ]; then
      echo "  WARNING: $service not healthy after ${timeout}s — check 'docker logs $cid'"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "  $service: healthy"
}
wait_healthy mysql "$ROOT"
wait_healthy mongo "$ROOT"
wait_healthy langfuse-db "$ROOT/deploy/observability"

cat <<'EOF'

======================================================================
 Ready. Services:

   MySQL             localhost:3306   (root/root, db: legacy_hrm)
   MongoDB           localhost:27017  (db: people_platform)
   Grafana           http://localhost:3000   (admin/admin, or anonymous)
   Langfuse          http://localhost:3001
   Prometheus        http://localhost:9090
   MinIO console     http://localhost:9001   (minio/miniosecret)

 First time only — Langfuse needs a project + API keys before tracing works:
   1. Open http://localhost:3001, sign up, create an org + project
   2. Copy its API keys into .env (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)
   3. python run_pipeline.py --verbose   # now traces to Langfuse too

 Dashboards (see README.md "Dashboards"):
   Langfuse -> Dashboards        (ships 4, pre-wired, no setup)
   Grafana -> Schema Field Mapper -> LLM Operations

 Pipeline dashboard UI:
   streamlit run app.py

 Stop everything (data is kept):
   ./scripts/stop.sh
======================================================================
EOF
