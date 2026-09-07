#!/usr/bin/env bash
# Restore from a backup directory produced by backup.sh.
#   ./deploy/scripts/restore.sh /var/backups/satya/20260728-020000
set -euo pipefail

SOURCE="${1:?usage: restore.sh <backup-directory>}"
[ -f "${SOURCE}/database.dump" ] || { echo "database.dump not found in ${SOURCE}"; exit 1; }

echo "This will REPLACE the current database and media. Type 'restore' to continue:"
read -r confirmation
[ "${confirmation}" = "restore" ] || { echo "aborted"; exit 1; }

(cd "${SOURCE}" && sha256sum -c CHECKSUMS)

docker compose -f docker-compose.prod.yml stop backend frontend

docker compose -f docker-compose.prod.yml exec -T db \
    pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
    < "${SOURCE}/database.dump"

docker run --rm \
    -v satya_media:/data \
    -v "${SOURCE}:/backup:ro" \
    alpine sh -c "rm -rf /data/* && tar xzf /backup/media.tar.gz -C /data"

docker compose -f docker-compose.prod.yml start backend frontend
echo "restore complete"
