#!/bin/sh
# v2.471.0 — fail2ban Phase 4c. Render envsubst placeholders in
# /etc/fail2ban/jail.d.template/*.conf into the writable
# /etc/fail2ban/jail.d/ before fail2ban-server starts. Only the
# FAIL2BAN_* env vars are substituted — unknown ${...} patterns in
# user-edited configs are passed through untouched (envsubst takes
# an explicit allowlist).
#
# Used as the entrypoint for the fail2ban service in
# docker-compose.yml. After rendering, exec's the upstream image
# entrypoint so locale + timezone setup runs normally.
set -e

# Allowlist of placeholders we render. Add new FAIL2BAN_* vars here
# when extending jail configs.
ALLOWED='${FAIL2BAN_LOGIN_MAXRETRY} ${FAIL2BAN_LOGIN_FINDTIME} ${FAIL2BAN_LOGIN_BANTIME} ${FAIL2BAN_MAGIC_LINK_REPLAY_BANTIME} ${FAIL2BAN_API_PROBE_MAXRETRY} ${FAIL2BAN_DEFAULT_BANTIME} ${FAIL2BAN_AUDIT_LOG_PATH}'

mkdir -p /etc/fail2ban/jail.d
rendered_count=0
for src in /etc/fail2ban/jail.d.template/*.conf; do
    [ -f "$src" ] || continue
    dst="/etc/fail2ban/jail.d/$(basename "$src")"
    envsubst "$ALLOWED" < "$src" > "$dst"
    rendered_count=$((rendered_count + 1))
done

echo "[render-jail.sh] rendered $rendered_count jail config file(s) into /etc/fail2ban/jail.d/"

# Hand off to the upstream crazymax/fail2ban entrypoint. The image
# ships its standard init at /entrypoint.sh; if a future image
# version moves it, update this exec line.
exec /entrypoint.sh "$@"
