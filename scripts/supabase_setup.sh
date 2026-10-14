#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
    value="${line#*=}"
    value="${value%\"}"
    value="${value#\"}"
    export "${line%%=*}=$value"
done < "$root/.env"

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL is missing from .env}"
: "${TANKERKOENIG_API_KEY:?TANKERKOENIG_API_KEY is missing from .env}"

for step in 000_extensions 001_schema 002_ingest 003_collector 004_schedule; do
    echo "applying $step"
    psql "$SUPABASE_DB_URL" -X -q -v ON_ERROR_STOP=1 -f "$root/supabase/$step.sql" -o /dev/null
done

echo "collector scheduled, the first prices land about ten minutes from now"
