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
SETTINGS_FILE="${BACKUP_DIR}/backup-settings.json"

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

mkdir -p "${BACKUP_DIR}" /var/log
touch /var/log/backup.log

# ── Demo mode: do nothing but idle ──────────────────────────────────────────
if is_truthy "${DEMO_MODE:-}"; then
    echo "[backup] DEMO_MODE — automated backups disabled" | tee -a /var/log/backup.log
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
${CRON_EXPR} POSTGRES_USER=${POSTGRES_USER} POSTGRES_PASSWORD=${POSTGRES_PASSWORD} POSTGRES_DB=${POSTGRES_DB} PGHOST=${PGHOST} BACKUP_DIR=${BACKUP_DIR} /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1
EOF
    echo "[backup] cron schedule: ${CRON_EXPR}" | tee -a /var/log/backup.log
}

install_crontab
echo "[backup] running initial backup on startup..." | tee -a /var/log/backup.log
POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" BACKUP_DIR="${BACKUP_DIR}" /bin/sh /usr/local/bin/backup.sh || true

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
        POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" BACKUP_DIR="${BACKUP_DIR}" /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1 || true
    fi
    sleep 30
done
