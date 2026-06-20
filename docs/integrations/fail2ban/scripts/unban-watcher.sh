#!/bin/sh
# v2.485.7 — fail2ban unban-request watcher.
#
# The admin-center service (running as the unprivileged appuser) can't
# reach fail2ban's root-only control socket, so its "Unban" button
# drops a request file into a shared control spool instead. This
# watcher runs INSIDE the (root) fail2ban container, drains the spool,
# and runs `fail2ban-client unban <ip>` for each request.
#
# Launched in the background by scripts/render-jail.sh before it exec's
# the fail2ban server. POSIX sh / busybox-safe.
#
# Request files: <spool>/unban-*.req, content = a single IP address.
# We re-sanitize the content to an IP charset before use so a malformed
# or hostile file can't inject shell — only [0-9a-fA-F:.] survives.

SPOOL="${FAIL2BAN_CONTROL_DIR:-/data/control}"
INTERVAL="${FAIL2BAN_UNBAN_POLL_SECONDS:-3}"

mkdir -p "$SPOOL" 2>/dev/null || true
echo "[unban-watcher] watching $SPOOL every ${INTERVAL}s"

while true; do
    for f in "$SPOOL"/unban-*.req; do
        [ -f "$f" ] || continue
        raw=$(cat "$f" 2>/dev/null)
        # Keep only IP-legal characters (digits, a-f, dot, colon).
        ip=$(printf '%s' "$raw" | tr -cd '0-9A-Fa-f:.')
        rm -f "$f"
        [ -n "$ip" ] || continue
        echo "[unban-watcher] unban $ip"
        # Global unban: clears the IP from every jail. Ignore errors
        # (already expired / not banned).
        fail2ban-client unban "$ip" >/dev/null 2>&1 || true
    done
    sleep "$INTERVAL"
done
