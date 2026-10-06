#!/bin/sh

set -e

echo "Ejecutando migraciones Alembic..."

alembic upgrade head

echo "Migraciones aplicadas correctamente."

exec "$@"