#!/bin/sh
# Installs a tiny cron job in the postgres:alpine sidecar.
set -eu

CRON_EXPR="${BACKUP_CRON:-0 3 * * *}"

# Build crontab. We pass env through to the script.
mkdir -p /etc/cron.d
cat > /etc/crontabs/root <<EOF
${CRON_EXPR} POSTGRES_USER=${POSTGRES_USER} POSTGRES_PASSWORD=${POSTGRES_PASSWORD} POSTGRES_DB=${POSTGRES_DB} PGHOST=${PGHOST} KEEP_DAILY=${KEEP_DAILY:-7} KEEP_WEEKLY=${KEEP_WEEKLY:-4} /bin/sh /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1
EOF

mkdir -p /var/log
touch /var/log/backup.log

echo "[backup] cron schedule: ${CRON_EXPR}"
echo "[backup] running initial backup on startup..."
POSTGRES_USER="${POSTGRES_USER}" POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" POSTGRES_DB="${POSTGRES_DB}" PGHOST="${PGHOST}" KEEP_DAILY="${KEEP_DAILY:-7}" KEEP_WEEKLY="${KEEP_WEEKLY:-4}" /bin/sh /usr/local/bin/backup.sh || true

# Run cron in foreground and tail the log
crond -f -L /var/log/cron.log &
exec tail -F /var/log/backup.log
