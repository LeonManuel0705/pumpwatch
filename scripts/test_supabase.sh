#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
port=$((54000 + RANDOM % 1000))

cleanup() {
    pg_ctl -D "$tmp/data" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$tmp"
}
trap cleanup EXIT

initdb -D "$tmp/data" -U postgres -A trust >/dev/null
pg_ctl -D "$tmp/data" -o "-p $port -k $tmp -c listen_addresses=''" -l "$tmp/server.log" -w start >/dev/null

run() {
    psql -X -q -v ON_ERROR_STOP=1 -h "$tmp" -p "$port" -U postgres -d postgres \
        -f "$root/supabase/$1" -o /dev/null 2>&1 | sed -n -e 's/^.*NOTICE:  //p' -e '/ERROR/p'
}

run test_setup.sql
run 001_schema.sql
run 002_ingest.sql
run 003_collector.sql
run test_ingest.sql
run test_collect.sql
run test_prune.sql
echo "all SQL checks passed"
