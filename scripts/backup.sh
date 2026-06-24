#!/bin/sh
# pg_dump + homebrew-volume tar + uploads-volume tar, with daily + weekly
# retention.
# Daily backups: kept for KEEP_DAILY days (default 7)
# Weekly backups (Sundays): kept for KEEP_WEEKLY weeks (default 4)
#
# v2.626.0 — a complete fresh-install restore needs three things, so each run
# produces THREE artefacts sharing one name stem (v2.631.1:
# YYYY-MM-DD_HHmmss[_<tag>] UTC, e.g. 2026-06-24_210306_manual):
#   <stem>.sql.gz          — full Postgres dump (every user + campaign +
#                            character + roll + setting; pg_dump of the whole DB)
#   <stem>.homebrew.tar.gz — the file-based homebrew content volume
#   <stem>.uploads.tar.gz  — the uploaded media volume (maps, portraits, tokens,
#                            audio, handouts, thumbnails) the DB rows reference
# Restore = load the SQL dump, then unpack the homebrew + uploads tarballs into
# their volumes. The shared stem pairs the three.
set -eu

# v2.620.0 — belt-and-braces: even a manual "run now" is a no-op in demo mode
# (the entrypoint already skips automated backups; this guards direct calls).
# v2.629.0 — DEMO_BACKUPS_ENABLED=true overrides the skip for testing.
_truthy() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;; *) return 1 ;;
    esac
}
if _truthy "${DEMO_MODE:-}" && ! _truthy "${DEMO_BACKUPS_ENABLED:-}"; then
    echo "[backup] DEMO_MODE — skipping backup (set DEMO_BACKUPS_ENABLED=true to override)"
    exit 0
fi

BACKUP_DIR="${BACKUP_DIR:-/backups}"
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
HOMEBREW_DIR="${HOMEBREW_DIR:-/homebrew}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
SETTINGS_FILE="${BACKUP_DIR}/backup-settings.json"
mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

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

# v2.631.1 — backup name stem: YYYY-MM-DD_HHmmss[_<tag>] (UTC). The trigger tag
# (manual / scheduled / startup) is slugified + length-capped for the filename;
# the full tag still goes in the sibling .tag file for the Admin Center column.
STEM="$(date -u +%Y-%m-%d_%H%M%S)"
TAG_SLUG="$(printf '%s' "${BACKUP_TAG:-}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed -e 's/--*/-/g' -e 's/^-//' -e 's/-$//' | cut -c1-30 | sed 's/-$//')"
[ -n "${TAG_SLUG}" ] && STEM="${STEM}_${TAG_SLUG}"

DAILY_SQL="${DAILY_DIR}/${STEM}.sql.gz"
DAILY_HB="${DAILY_DIR}/${STEM}.homebrew.tar.gz"
DAILY_UP="${DAILY_DIR}/${STEM}.uploads.tar.gz"

echo "[backup] writing ${DAILY_SQL}"
# --clean --if-exists makes the dump self-restoring: it drops each object
# (IF EXISTS) before recreating it, so a restore can pipe it straight into the
# live database without a manual schema wipe (see entrypoint-backup.sh).
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump --clean --if-exists \
    -h "${PGHOST:-db}" -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
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

# v2.630.8 — record how this run was triggered (scheduled / manual / startup /
# pre-restore safety) as a sibling .tag file the Admin Center shows in the Tag
# column. Written before the Sunday weekly copy so the weekly set gets it too.
DAILY_TAG="${DAILY_DIR}/${STEM}.tag"
if [ -n "${BACKUP_TAG:-}" ]; then
    printf '%s' "${BACKUP_TAG}" > "${DAILY_TAG}"
fi

# On Sundays also stash a weekly copy of all three artefacts (+ the tag)
if [ "${DOW}" = "7" ]; then
    cp "${DAILY_SQL}" "${WEEKLY_DIR}/${STEM}.sql.gz"
    cp "${DAILY_HB}"  "${WEEKLY_DIR}/${STEM}.homebrew.tar.gz"
    cp "${DAILY_UP}"  "${WEEKLY_DIR}/${STEM}.uploads.tar.gz"
    [ -f "${DAILY_TAG}" ] && cp "${DAILY_TAG}" "${WEEKLY_DIR}/${STEM}.tag"
    echo "[backup] copied to weekly"
fi

# Retention: prune daily older than KEEP_DAILY, weekly older than KEEP_WEEKLY*7
find "${DAILY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' -o -name '*.uploads.tar.gz' \) \
    -mtime +"${KEEP_DAILY}" -print -delete || true
WEEKLY_DAYS=$(( KEEP_WEEKLY * 7 ))
find "${WEEKLY_DIR}" -type f \( -name '*.sql.gz' -o -name '*.homebrew.tar.gz' -o -name '*.uploads.tar.gz' -o -name '*.tag' \) \
    -mtime +"${WEEKLY_DAYS}" -print -delete || true
find "${DAILY_DIR}" -type f -name '*.tag' -mtime +"${KEEP_DAILY}" -print -delete || true

echo "[backup] done at $(date -u)"
