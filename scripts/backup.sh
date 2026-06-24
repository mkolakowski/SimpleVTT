#!/bin/sh
# pg_dump + homebrew-volume tar + uploads-volume tar, with daily + weekly
# retention.
# Daily backups: kept for KEEP_DAILY days (default 7)
# Weekly backups (Sundays): kept for KEEP_WEEKLY weeks (default 4)
#
# v2.626.0 — a complete fresh-install restore needs three things, so each run
# now produces THREE artefacts sharing one timestamp:
#   simplevtt-<ts>.sql.gz          — full Postgres dump (every user + campaign +
#                                     character + roll + setting; pg_dump of the
#                                     whole database)
#   simplevtt-<ts>.homebrew.tar.gz — the file-based homebrew content volume
#   simplevtt-<ts>.uploads.tar.gz  — the uploaded media volume (maps, portraits,
#                                     tokens, audio, handouts, thumbnails) that
#                                     the DB rows reference by URL
# Restore = load the SQL dump, then unpack the homebrew + uploads tarballs into
# their volumes. The shared timestamp pairs the three.
set -eu

# v2.620.0 — belt-and-braces: even a manual "run now" is a no-op in demo mode
# (the entrypoint already skips automated backups; this guards direct calls).
case "$(printf '%s' "${DEMO_MODE:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
        echo "[backup] DEMO_MODE — skipping backup"
        exit 0 ;;
esac

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
HOMEBREW_DIR="${HOMEBREW_DIR:-/homebrew}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
SETTINGS_FILE="${BACKUP_DIR}/backup-settings.json"
mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

TS=$(date -u +%Y%m%dT%H%M%SZ)
DOW=$(date -u +%u)   # 1..7, 7 = Sunday

# v2.620.0 — retention is operator-editable from the Admin Center, written to
# backup-settings.json. Prefer the file's values; fall back to the env.
json_num() {
    sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p" "$1" 2>/dev/null | head -n1
}
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
if [ -f "${SETTINGS_FILE}" ]; then
    _kd="$(json_num "${SETTINGS_FILE}" keep_daily)"; [ -n "${_kd}" ] && KEEP_DAILY="${_kd}"
    _kw="$(json_num "${SETTINGS_FILE}" keep_weekly)"; [ -n "${_kw}" ] && KEEP_WEEKLY="${_kw}"
fi

DAILY_SQL="${DAILY_DIR}/simplevtt-${TS}.sql.gz"
DAILY_HB="${DAILY_DIR}/simplevtt-${TS}.homebrew.tar.gz"
DAILY_UP="${DAILY_DIR}/simplevtt-${TS}.uploads.tar.gz"

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

# Uploaded media (maps / portraits / tokens / audio / handouts / thumbnails).
# The DB rows reference these by /static/uploads/... URL, so a fresh-install
# restore needs them too. Same empty-dir-still-valid-tarball rule.
echo "[backup] writing ${DAILY_UP}"
if [ -d "${UPLOADS_DIR}" ]; then
    tar -czf "${DAILY_UP}" -C "${UPLOADS_DIR}" .
else
    tar -czf "${DAILY_UP}" -T /dev/null
fi

# On Sundays also stash a weekly copy of all three artefacts
if [ "${DOW}" = "7" ]; then
    cp "${DAILY_SQL}" "${WEEKLY_DIR}/simplevtt-${TS}.sql.gz"
    cp "${DAILY_HB}"  "${WEEKLY_DIR}/simplevtt-${TS}.homebrew.tar.gz"
    cp "${DAILY_UP}"  "${WEEKLY_DIR}/simplevtt-${TS}.uploads.tar.gz"
    echo "[backup] copied to weekly"
fi

# Retention: prune daily older than KEEP_DAILY, weekly older than KEEP_WEEKLY*7
find "${DAILY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' -o -name '*.uploads.tar.gz' \) \
    -mtime +"${KEEP_DAILY}" -print -delete || true
WEEKLY_DAYS=$(( KEEP_WEEKLY * 7 ))
find "${WEEKLY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' -o -name '*.uploads.tar.gz' \) \
    -mtime +"${WEEKLY_DAYS}" -print -delete || true

echo "[backup] done at $(date -u)"
