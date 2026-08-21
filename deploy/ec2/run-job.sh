#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/nasa-etl"
ENV_FILE="/etc/nasa-etl/nasa-etl.env"
COMPOSE_FILE="$APP_DIR/deploy/compose/docker-compose.ec2.yml"
COMPOSE=(/usr/bin/docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

"${COMPOSE[@]}" up -d postgres

for attempt in {1..30}; do
  if "${COMPOSE[@]}" exec -T postgres sh -ec 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'; then
    exec "${COMPOSE[@]}" run --rm --no-deps nasa-etl
  fi
  sleep 2
done

echo "PostgreSQL não ficou pronto após 60 segundos." >&2
exit 1
