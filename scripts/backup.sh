#!/bin/sh
# Copia PostgreSQL y archivos en una carpeta privada; usa el proyecto Compose activo.
set -eu
backup_directory=${1:?Usage: scripts/backup.sh destination-directory}
umask 077
mkdir -p "$backup_directory"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_directory/database.dump"
docker compose exec -T api tar -C /workspace -czf - . > "$backup_directory/workspace.tar.gz"
# Verifica que el dump y el archivo tar puedan ser leídos.
docker compose exec -T db pg_restore --list < "$backup_directory/database.dump" > /dev/null
tar -tzf "$backup_directory/workspace.tar.gz" > /dev/null
