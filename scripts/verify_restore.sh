#!/bin/sh
# Restaura únicamente en un contenedor temporal aislado y lo elimina al terminar.
set -eu
dump_file=${1:?Usage: scripts/verify_restore.sh path-to-database.dump}
restore_container="chatbot-restore-check-$$"
cleanup() { docker rm -f "$restore_container" > /dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
docker run -d --name "$restore_container" -e POSTGRES_PASSWORD=temporary-restore-only pgvector/pgvector:pg16 > /dev/null
attempt=0
until docker exec "$restore_container" pg_isready -U postgres > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 30 ] || exit 1
    sleep 1
done
docker exec -i "$restore_container" pg_restore -U postgres -d postgres --exit-on-error < "$dump_file"
docker exec "$restore_container" pg_dump -U postgres -d postgres --schema-only > /dev/null
