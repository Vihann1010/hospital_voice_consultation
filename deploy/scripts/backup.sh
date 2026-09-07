#!/usr/bin/env bash
# Nightly backup of the database and the media volume.
#
#   0 2 * * *  /opt/satya/deploy/scripts/backup.sh >> /var/log/satya-backup.log 2>&1
#
# Media (recordings, reports, prescription PDFs) is part of the medical record,
# so backing up Postgres alone is not enough.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/satya}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${TARGET}"

echo "[$(date -Is)] backing up database…"
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --format=custom \
    > "${TARGET}/database.dump"

echo "[$(date -Is)] backing up media…"
docker run --rm \
    -v satya_media:/data:ro \
    -v "${TARGET}:/backup" \
    alpine tar czf /backup/media.tar.gz -C /data .

sha256sum "${TARGET}"/* > "${TARGET}/CHECKSUMS"

echo "[$(date -Is)] pruning backups older than ${RETENTION_DAYS} days…"
find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} +

echo "[$(date -Is)] backup complete: ${TARGET}"
du -sh "${TARGET}"
