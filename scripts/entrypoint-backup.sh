#!/bin/sh
# Backup sidecar entrypoint.
#
# v2.620.0 — the schedule + retention are now operator-editable at runtime
# from the Admin Center, which writes ${BACKUP_DIR}/backup-settings.json on
# the shared backup volume. This script:
#   - skips ALL automated backups when DEMO_MODE is truthy (the demo DB
#     reseeds hourly, so scheduled dumps are pure churn);
#   - otherwise installs cron from the settings file (falling back to the
#     BACKUP_CRON env on first boot, before any file exists) and watches the
#     file, regenerating the crontab whenever it changes.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
HOMEBREW_DIR="${HOMEBREW_DIR:-/homebrew}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
SETTINGS_FILE="${BACKUP_DIR}/backup-settings.json"
RESTORE_TRIGGER="${BACKUP_DIR}/.restore-request"
RESTORE_RESULT="${BACKUP_DIR}/.restore-result"

is_truthy() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

# Tiny JSON string/number field reader (cron is a string, retention numbers).
# Avoids a jq dependency in the postgres:alpine image.
json_field() {
    # $1 = file, $2 = key
    sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" "$1" 2>/dev/null | head -n1
}

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" /var/log
# v2.630.7: the Admin Center process (runs as appuser) drops control files into
# ${BACKUP_DIR} — the run-now / restore-request triggers + backup-settings.json.
# This sidecar created the dir as root, so make it sticky world-writable (like
# /tmp) so those writes don't fail with EACCES. Without this, "Back up now" 500s.
# v2.632.0: the artifact dirs are world-writable (no sticky) so the Admin Center
# (appuser) can also DELETE backups the sidecar wrote as root. Internal volume,
# operator-gated — same trust boundary as the restore trigger.
chmod 1777 "${BACKUP_DIR}" 2>/dev/null || true
chmod 0777 "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" 2>/dev/null || true
touch /var/log/backup.log

# ── Demo mode: do nothing but idle ──────────────────────────────────────────
# DEMO_BACKUPS_ENABLED is a testing override — when truthy, backups run normally
# even on a demo instance (so the backup/restore flow can be exercised). Default
# off, so a plain demo still skips the churn.
if is_truthy "${DEMO_MODE:-}" && ! is_truthy "${DEMO_BACKUPS_ENABLED:-}"; then
    echo "[backup] DEMO_MODE — automated backups disabled (set DEMO_BACKUPS_ENABLED=true to override)" | tee -a /var/log/backup.log
    # Stay up (so the service stays "running") and tail the log.
    exec tail -F /var/log/backup.log
fi

# Resolve the effective cron expression: settings file wins, else env default.
effective_cron() {
    if [ -f "${SETTINGS_FILE}" ]; then
        c="$(json_field "${SETTINGS_FILE}" cron)"
        if [ -n "${c}" ]; then
            printf '%s' "${c}"
            return 0
        fi
    fi
    printf '%s' "${BACKUP_CRON:-0 3 * * *}"
}

install_crontab() {
    CRON_EXPR="$(effective_cron)"
    cat > /etc/crontabs/root <<EOF
${CRON_EXPR} POSTGRES_USER=${POSTGRES_USER} POSTGRES_PASSWORD=${POSTGRES_PASSWORD} POSTGRES_DB=${POSTGRES_DB} PGHOST=${PGHOST} BACKUP_DIR=${BACKUP_DIR} BACKUP_TAG=scheduled /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1
EOF
    echo "[backup] cron schedule: ${CRON_EXPR}" | tee -a /var/log/backup.log
}

# ── Restore (v2.627.0) ───────────────────────────────────────────────────────
# Driven by a ``.restore-request`` JSON trigger the Admin Center drops on the
# shared volume ({"bucket","ts"}). DESTRUCTIVE: it overwrites the live database
# + homebrew + uploads with the selected backup — so it ALWAYS takes a fresh,
# tagged safety backup first. Never reached in DEMO_MODE (the script execs into
# the idle tail above before the watch loop). The result is written to
# ``.restore-result`` for the page to surface.
do_restore() {
    bucket="$(json_field "${RESTORE_TRIGGER}" bucket)"
    ts="$(json_field "${RESTORE_TRIGGER}" ts)"
    rm -f "${RESTORE_TRIGGER}"
    src="${BACKUP_DIR}/${bucket}"
    sql="${src}/${ts}.sql.gz"
    hb="${src}/${ts}.homebrew.tar.gz"
    up="${src}/${ts}.uploads.tar.gz"
    if [ -z "${bucket}" ] || [ -z "${ts}" ] || [ ! -f "${sql}" ]; then
        printf '{"ok":false,"ts":"%s","error":"backup not found"}' "${ts}" > "${RESTORE_RESULT}"
        echo "[backup] restore: backup ${bucket}/${ts} not found — aborting" | tee -a /var/log/backup.log
        return
    fi

    echo "[backup] restore: taking a tagged safety backup before restoring ${ts}" | tee -a /var/log/backup.log
    BACKUP_TAG="pre-restore safety backup (before restoring ${ts})" \
    POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" BACKUP_DIR="${BACKUP_DIR}" \
        /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1 || true

    echo "[backup] restore: loading database from ${ts}" | tee -a /var/log/backup.log
    db_ok=1
    gunzip -c "${sql}" | PGPASSWORD="${POSTGRES_PASSWORD}" psql -v ON_ERROR_STOP=0 \
        -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >> /var/log/backup.log 2>&1 || db_ok=0

    # Homebrew + uploads volumes: clear then unpack (these mounts are RW).
    if [ -f "${hb}" ] && [ -d "${HOMEBREW_DIR}" ]; then
        echo "[backup] restore: unpacking homebrew volume" | tee -a /var/log/backup.log
        find "${HOMEBREW_DIR}" -mindepth 1 -delete 2>/dev/null || true
        tar -xzf "${hb}" -C "${HOMEBREW_DIR}" >> /var/log/backup.log 2>&1 || true
    fi
    if [ -f "${up}" ] && [ -d "${UPLOADS_DIR}" ]; then
        echo "[backup] restore: unpacking uploads volume" | tee -a /var/log/backup.log
        find "${UPLOADS_DIR}" -mindepth 1 -delete 2>/dev/null || true
        tar -xzf "${up}" -C "${UPLOADS_DIR}" >> /var/log/backup.log 2>&1 || true
    fi

    printf '{"ok":true,"ts":"%s","db_ok":%s,"at":"%s"}' \
        "${ts}" "${db_ok}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${RESTORE_RESULT}"
    echo "[backup] restore: done (ts=${ts}, db_ok=${db_ok})" | tee -a /var/log/backup.log
}

install_crontab
echo "[backup] running initial backup on startup..." | tee -a /var/log/backup.log
POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" BACKUP_DIR="${BACKUP_DIR}" BACKUP_TAG="startup" /bin/sh /usr/local/bin/backup.sh || true

crond -L /var/log/cron.log

# ── Watch loop: regenerate crontab on settings change + honor "run now" ──────
# crond re-reads /etc/crontabs each minute, so rewriting the file is enough.
LAST_MTIME=""
RUN_TRIGGER="${BACKUP_DIR}/.run-now"
( tail -F /var/log/backup.log & ) >/dev/null 2>&1
while true; do
    if [ -f "${SETTINGS_FILE}" ]; then
        MTIME="$(stat -c %Y "${SETTINGS_FILE}" 2>/dev/null || echo '')"
        if [ "${MTIME}" != "${LAST_MTIME}" ]; then
            LAST_MTIME="${MTIME}"
            install_crontab
        fi
    fi
    if [ -f "${RUN_TRIGGER}" ]; then
        rm -f "${RUN_TRIGGER}"
        echo "[backup] run-now trigger — taking an on-demand backup" | tee -a /var/log/backup.log
        POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" BACKUP_DIR="${BACKUP_DIR}" BACKUP_TAG="manual" /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1 || true
    fi
    if [ -f "${RESTORE_TRIGGER}" ]; then
        do_restore
    fi
    # v2.633.0 — short poll so "Back up now" / restore triggers fire promptly
    # (the progress toast on the page tracks the run live).
    sleep 2
done
