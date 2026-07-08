#!/bin/sh
# v2.474.0 — drop the SimpleVTT app from root to `appuser` at
# container start.
#
# The container starts as root so the entrypoint can chown the
# mount points of named volumes (uploads_data, homebrew_data,
# audit_logs) — those inherit root ownership from whichever
# process first created them, which can be a fresh image build or
# an upgrade from a pre-v2.474.0 deploy. After fixing perms we
# drop to the unprivileged `appuser` via gosu and exec the
# command we were called with.
#
# Why gosu and not su / sudo: gosu is a tiny single-file tool that
# does `setuid + setgid + exec`; no PAM, no `init` reparenting,
# no TTY allocation. Signals (SIGTERM from compose stop) reach
# uvicorn cleanly.

set -e

# Mount points the running app needs to write to. Each is owned
# by the named volume in docker-compose.yml; on first mount the
# volume inherits the directory's ownership from the image (root),
# which we fix here. Idempotent: chown -R on already-owned paths
# is a no-op.
APP_PATHS="
/app/app/static/uploads
/app/app/data/homebrew
/var/log/simplevtt
/data/control
/data/selftest-results
"

for p in $APP_PATHS; do
    if [ -d "$p" ]; then
        chown -R appuser:appuser "$p" 2>/dev/null || true
    fi
done

# Drop privileges and exec. `gosu` replaces the current process,
# preserving PID 1 semantics so uvicorn receives signals directly.
exec gosu appuser "$@"
