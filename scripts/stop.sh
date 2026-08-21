#!/usr/bin/env bash
# Stops every container start.sh started.
#
# Observability stack data (Langfuse project/keys, Grafana, Prometheus/Loki/
# Tempo) lives in named Docker volumes and survives this — start.sh again
# picks up right where you left off.
#
# MySQL/MongoDB have no persistent volume by design: they exist to demo the
# two schemas, not to hold state, and are re-seeded from
# docker/mysql-init + docker/mongo-init on every start.sh anyway.
#
# Usage: ./scripts/stop.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Stopping observability stack =="
(cd deploy/observability && docker compose down)

echo
echo "== Stopping app databases =="
docker compose down

cat <<'EOF'

All containers stopped and removed. Observability data (Langfuse project/
keys, dashboards, metrics/logs/traces) was kept.

To wipe the observability data too (irreversible), run it yourself:
  (cd deploy/observability && docker compose down -v)
EOF
