#!/bin/sh
# pg_dump + homebrew-volume tar, with daily + weekly retention.
# Daily backups: kept for KEEP_DAILY days (default 7)
# Weekly backups (Sundays): kept for KEEP_WEEKLY weeks (default 4)
#
# Two artefacts are produced each run:
#   simplevtt-<ts>.sql.gz   — Postgres dump
#   simplevtt-<ts>.homebrew.tar.gz — tarball of the file-based homebrew volume
# Both share the same timestamp so a restore script can pair them.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
HOMEBREW_DIR="${HOMEBREW_DIR:-/homebrew}"
mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

TS=$(date -u +%Y%m%dT%H%M%SZ)
DOW=$(date -u +%u)   # 1..7, 7 = Sunday
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"

DAILY_SQL="${DAILY_DIR}/simplevtt-${TS}.sql.gz"
DAILY_HB="${DAILY_DIR}/simplevtt-${TS}.homebrew.tar.gz"

echo "[backup] writing ${DAILY_SQL}"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h "${PGHOST:-db}" -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip -9 > "${DAILY_SQL}"

# Homebrew is file-based; tar the volume if it exists and has content. An
# empty or missing directory still produces a valid (tiny) tarball so the
# restore story stays uniform.
echo "[backup] writing ${DAILY_HB}"
if [ -d "${HOMEBREW_DIR}" ]; then
    tar -czf "${DAILY_HB}" -C "${HOMEBREW_DIR}" .
else
    tar -czf "${DAILY_HB}" -T /dev/null
fi

# On Sundays also stash a weekly copy of both artefacts
if [ "${DOW}" = "7" ]; then
    cp "${DAILY_SQL}" "${WEEKLY_DIR}/simplevtt-${TS}.sql.gz"
    cp "${DAILY_HB}"  "${WEEKLY_DIR}/simplevtt-${TS}.homebrew.tar.gz"
    echo "[backup] copied to weekly"
fi

# Retention: prune daily older than KEEP_DAILY, weekly older than KEEP_WEEKLY*7
find "${DAILY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' \) \
    -mtime +"${KEEP_DAILY}" -print -delete || true
WEEKLY_DAYS=$(( KEEP_WEEKLY * 7 ))
find "${WEEKLY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' \) \
    -mtime +"${WEEKLY_DAYS}" -print -delete || true

echo "[backup] done at $(date -u)"
