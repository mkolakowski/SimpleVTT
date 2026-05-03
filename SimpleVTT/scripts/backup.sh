#!/bin/sh
# pg_dump with daily + weekly retention.
# Daily backups: kept for KEEP_DAILY days (default 7)
# Weekly backups (Sundays): kept for KEEP_WEEKLY weeks (default 4)
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

TS=$(date -u +%Y%m%dT%H%M%SZ)
DOW=$(date -u +%u)   # 1..7, 7 = Sunday
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"

DAILY_FILE="${DAILY_DIR}/simplevtt-${TS}.sql.gz"
echo "[backup] writing ${DAILY_FILE}"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h "${PGHOST:-db}" -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip -9 > "${DAILY_FILE}"

# On Sundays also stash a weekly copy
if [ "${DOW}" = "7" ]; then
    cp "${DAILY_FILE}" "${WEEKLY_DIR}/simplevtt-${TS}.sql.gz"
    echo "[backup] copied to weekly"
fi

# Retention: prune daily older than KEEP_DAILY, weekly older than KEEP_WEEKLY*7
find "${DAILY_DIR}" -type f -name '*.sql.gz' -mtime +"${KEEP_DAILY}" -print -delete || true
WEEKLY_DAYS=$(( KEEP_WEEKLY * 7 ))
find "${WEEKLY_DIR}" -type f -name '*.sql.gz' -mtime +"${WEEKLY_DAYS}" -print -delete || true

echo "[backup] done at $(date -u)"
