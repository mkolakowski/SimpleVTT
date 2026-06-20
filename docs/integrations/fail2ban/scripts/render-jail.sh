#!/bin/sh
# v2.471.0 — fail2ban Phase 4c. Render ${VAR} placeholders in
# /etc/fail2ban/jail.d.template/*.conf (Phase 4c) AND
# /etc/fail2ban/action.d.template/*.conf (Phase 4d) into the
# writable /etc/fail2ban/{jail,action}.d/ before fail2ban-server
# starts.
#
# **POSIX shell, no envsubst.** v2.473.1 — the crazymax/fail2ban
# 1.0.2 base is alpine + busybox and doesn't ship `gettext`'s
# envsubst. Earlier draft used envsubst and crash-looped the
# container; current implementation uses sed with `|` as the
# delimiter so paths with `/` aren't a problem. The allowlist
# below names every env var we substitute — unknown ${...}
# patterns in operator-edited configs pass through untouched.
#
# Used as the entrypoint for the fail2ban service in
# docker-compose.yml. After rendering, exec's the upstream image
# entrypoint at /entrypoint.sh.
set -e

VARS='FAIL2BAN_LOGIN_MAXRETRY FAIL2BAN_LOGIN_FINDTIME FAIL2BAN_LOGIN_BANTIME FAIL2BAN_MAGIC_LINK_REPLAY_BANTIME FAIL2BAN_API_PROBE_MAXRETRY FAIL2BAN_DEFAULT_BANTIME FAIL2BAN_AUDIT_LOG_PATH FAIL2BAN_ACTION CLOUDFLARE_API_TOKEN CLOUDFLARE_ZONE_ID CLOUDFLARE_API_BASE_URL'

render_one() {
    src="$1"
    dst="$2"
    cp "$src" "$dst"
    for var in $VARS; do
        # POSIX-compliant indirect variable read.
        eval "value=\"\${$var:-}\""
        # Escape backslash + ampersand + the | delimiter for sed.
        esc=$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')
        # Use | as the delimiter so values containing / don't need
        # escaping (URLs, file paths, etc.).
        sed -i "s|\${$var}|$esc|g" "$dst"
    done
}

# v2.473.1 — write rendered configs to /data/{jail.d,action.d}.
# The crazymax/fail2ban image's standard entrypoint symlinks
# /data/<dir> → /etc/fail2ban/<dir>; if we write directly to
# /etc/fail2ban/ first, the image's `ln -s` fails with "File
# exists" and the container crash-loops. Writing into /data/
# means the image's symlink step picks up our rendered configs
# in its normal flow.
mkdir -p /data/jail.d
jail_count=0
for src in /etc/fail2ban/jail.d.template/*.conf; do
    [ -f "$src" ] || continue
    render_one "$src" "/data/jail.d/$(basename "$src")"
    jail_count=$((jail_count + 1))
done

action_count=0
if [ -d /etc/fail2ban/action.d.template ]; then
    mkdir -p /data/action.d
    for src in /etc/fail2ban/action.d.template/*.conf; do
        [ -f "$src" ] || continue
        render_one "$src" "/data/action.d/$(basename "$src")"
        action_count=$((action_count + 1))
    done
fi

echo "[render-jail.sh] rendered $jail_count jail + $action_count action config file(s) into /data/"

# Hand off to the upstream crazymax/fail2ban entrypoint. It
# symlinks /data/{jail,action,filter}.d into /etc/fail2ban/ as
# part of its init.
exec /entrypoint.sh "$@"
