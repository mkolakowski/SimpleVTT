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

# Allowlist of placeholders we render. Add new FAIL2BAN_* and
# CLOUDFLARE_* vars here when extending jail / action configs.
# Phase 4d (v2.472.0) added the FAIL2BAN_ACTION + CLOUDFLARE_*
# entries so action.d/cloudflare-bouncer.conf's [Init] section
# resolves cleanly.
ALLOWED='${FAIL2BAN_LOGIN_MAXRETRY} ${FAIL2BAN_LOGIN_FINDTIME} ${FAIL2BAN_LOGIN_BANTIME} ${FAIL2BAN_MAGIC_LINK_REPLAY_BANTIME} ${FAIL2BAN_API_PROBE_MAXRETRY} ${FAIL2BAN_DEFAULT_BANTIME} ${FAIL2BAN_AUDIT_LOG_PATH} ${FAIL2BAN_ACTION} ${CLOUDFLARE_API_TOKEN} ${CLOUDFLARE_ZONE_ID} ${CLOUDFLARE_API_BASE_URL}'

mkdir -p /etc/fail2ban/jail.d
jail_count=0
for src in /etc/fail2ban/jail.d.template/*.conf; do
    [ -f "$src" ] || continue
    dst="/etc/fail2ban/jail.d/$(basename "$src")"
    envsubst "$ALLOWED" < "$src" > "$dst"
    jail_count=$((jail_count + 1))
done

# v2.472.0 — Phase 4d. Render action.d/*.conf too so the [Init]
# blocks resolve their CLOUDFLARE_* placeholders. The image's
# built-in action.d/* files stay untouched (they live at
# /etc/fail2ban/action.d/ and we only add new files there).
action_count=0
if [ -d /etc/fail2ban/action.d.template ]; then
    mkdir -p /etc/fail2ban/action.d
    for src in /etc/fail2ban/action.d.template/*.conf; do
        [ -f "$src" ] || continue
        dst="/etc/fail2ban/action.d/$(basename "$src")"
        envsubst "$ALLOWED" < "$src" > "$dst"
        action_count=$((action_count + 1))
    done
fi

echo "[render-jail.sh] rendered $jail_count jail + $action_count action config file(s)"

# Hand off to the upstream crazymax/fail2ban entrypoint. The image
# ships its standard init at /entrypoint.sh; if a future image
# version moves it, update this exec line.
exec /entrypoint.sh "$@"
