#!/bin/sh
# Offsite (cloud) backup upload helpers — v2.998.0.
#
# Sourced by backup.sh (push after each run) and entrypoint-backup.sh (the
# .offsite-test / .offsite-push trigger files the Admin Center drops). The
# uploader is rclone (baked into the sidecar image via Dockerfile.backup); one
# remote named ``offsite`` is defined in ${BACKUP_DIR}/rclone.conf, which the
# Admin Center writes from its web form (S3 keys, or a pasted OAuth token for
# Google Drive / Dropbox / OneDrive). Settings (enabled / mode / path) live in
# backup-settings.json next to the schedule + retention.
#
# Modes:
#   copy — accumulate: remote only ever gains files (survives local
#          corruption; grows unbounded).                      [default]
#   sync — mirror: local retention pruning propagates, remote stays bounded.
#
# Upload failures NEVER fail the backup run — the artefacts are already safe
# on the local volume; the failure is recorded in .offsite-status for the
# Admin Center to surface.
#
# This file must stay POSIX-sh (busybox ash) and self-contained: it defines
# its own JSON field reader and derives every path from BACKUP_DIR so both
# callers (cron env and the watch loop) work without extra exports.

_oj_field() {
    # $1 = file, $2 = key — tiny jq-free JSON scalar reader (same pattern as
    # entrypoint-backup.sh's json_field; handles quoted + bare values).
    sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\)\"\{0,1\}.*/\1/p" "$1" 2>/dev/null | head -n1
}

_offsite_settings() { printf '%s' "${BACKUP_DIR:-/backups}/backup-settings.json"; }
_offsite_conf()     { printf '%s' "${BACKUP_DIR:-/backups}/rclone.conf"; }

# Conservative network limits so a bad endpoint/credentials can't wedge a
# backup run or the watch loop for long.
_RCLONE_COMMON="--contimeout 10s --timeout 5m --retries 2 --low-level-retries 4"

offsite_enabled() {
    # Enabled = the settings flag is true AND a remote config exists.
    [ -f "$(_offsite_conf)" ] || return 1
    [ -f "$(_offsite_settings)" ] || return 1
    [ "$(_oj_field "$(_offsite_settings)" offsite_enabled)" = "true" ]
}

_offsite_mode() {
    m="$(_oj_field "$(_offsite_settings)" offsite_mode)"
    [ "${m}" = "sync" ] && printf 'sync' || printf 'copy'
}

_offsite_path() {
    p="$(_oj_field "$(_offsite_settings)" offsite_path)"
    [ -n "${p}" ] && printf '%s' "${p}" || printf 'simplevtt-backups'
}

_offsite_json_escape() {
    # Newlines → spaces, then escape backslashes + double quotes for JSON.
    printf '%s' "$1" | tr '\n\r' '  ' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

offsite_push() {
    # Upload daily/ + weekly/ to the offsite remote per the configured mode.
    # Writes ${BACKUP_DIR}/.offsite-status {ok, at, mode, path, error?, ts?}.
    bdir="${BACKUP_DIR:-/backups}"
    mode="$(_offsite_mode)"
    rpath="$(_offsite_path)"
    ok=1
    err=""
    for bucket in daily weekly; do
        [ -d "${bdir}/${bucket}" ] || continue
        out="$(rclone --config "$(_offsite_conf)" ${_RCLONE_COMMON} \
                "${mode}" "${bdir}/${bucket}" "offsite:${rpath}/${bucket}" \
                --exclude '*.tmp' 2>&1)" || {
            ok=0
            err="rclone ${mode} ${bucket}: $(printf '%s' "${out}" | tail -n1)"
        }
        printf '%s\n' "${out}" >> /var/log/backup.log 2>/dev/null || true
    done
    if [ "${ok}" = "1" ]; then
        printf '{"ok":true,"at":"%s","mode":"%s","path":"%s","ts":"%s"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${mode}" \
            "$(_offsite_json_escape "${rpath}")" "${1:-}" \
            > "${bdir}/.offsite-status" 2>/dev/null || true
        echo "[backup] offsite: ${mode} to offsite:${rpath} OK" | tee -a /var/log/backup.log
    else
        printf '{"ok":false,"at":"%s","mode":"%s","path":"%s","error":"%s"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${mode}" \
            "$(_offsite_json_escape "${rpath}")" "$(_offsite_json_escape "${err}")" \
            > "${bdir}/.offsite-status" 2>/dev/null || true
        echo "[backup] offsite: FAILED — ${err}" | tee -a /var/log/backup.log
    fi
}

offsite_list() {
    # List the remote daily/ + weekly/ artefacts (rclone lsjson emits a JSON
    # array) into ${BACKUP_DIR}/.offsite-listing {ok, at, daily:[…], weekly:[…]}
    # for the Admin Center's remote-backups browser. v2.1000.0.
    bdir="${BACKUP_DIR:-/backups}"
    rpath="$(_offsite_path)"
    if [ ! -f "$(_offsite_conf)" ]; then
        printf '{"ok":false,"at":"%s","error":"no offsite config"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${bdir}/.offsite-listing" 2>/dev/null || true
        return
    fi
    ok=1
    daily="[]"
    weekly="[]"
    for bucket in daily weekly; do
        out="$(rclone --config "$(_offsite_conf)" \
                --contimeout 10s --timeout 60s --retries 1 --low-level-retries 2 \
                lsjson "offsite:${rpath}/${bucket}" 2>&1)" || {
            # A missing remote dir is an empty listing, not an error; anything
            # else (auth/network) marks the listing failed.
            case "${out}" in
                *"directory not found"*|*"error 404"*) out="[]" ;;
                *) ok=0 ;;
            esac
        }
        case "${out}" in \[*) ;; *) out="[]" ;; esac   # only embed a JSON array
        [ "${bucket}" = "daily" ] && daily="${out}" || weekly="${out}"
    done
    if [ "${ok}" = "1" ]; then
        printf '{"ok":true,"at":"%s","path":"%s","daily":%s,"weekly":%s}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${rpath}")" \
            "${daily}" "${weekly}" > "${bdir}/.offsite-listing" 2>/dev/null || true
        echo "[backup] offsite list: offsite:${rpath} listed" | tee -a /var/log/backup.log
    else
        printf '{"ok":false,"at":"%s","path":"%s","error":"listing failed (see backup.log)"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${rpath}")" \
            > "${bdir}/.offsite-listing" 2>/dev/null || true
        echo "[backup] offsite list: FAILED" | tee -a /var/log/backup.log
    fi
}

offsite_pull() {
    # Download one remote backup run's artefacts into the LOCAL bucket dir so
    # the existing (gated) restore flow can take over. Trigger JSON supplies
    # {bucket, ts}; both are re-validated here (charset) so a crafted trigger
    # can't traverse. Writes ${BACKUP_DIR}/.offsite-pull-result. v2.1000.0.
    bdir="${BACKUP_DIR:-/backups}"
    rpath="$(_offsite_path)"
    bucket="$1"
    ts="$2"
    fail_pull() {
        printf '{"ok":false,"at":"%s","ts":"%s","error":"%s"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${ts}")" \
            "$(_offsite_json_escape "$1")" > "${bdir}/.offsite-pull-result" 2>/dev/null || true
        echo "[backup] offsite pull: FAILED — $1" | tee -a /var/log/backup.log
    }
    case "${bucket}" in daily|weekly) ;; *) fail_pull "bad bucket"; return ;; esac
    case "${ts}" in ''|*[!A-Za-z0-9_-]*) fail_pull "bad timestamp"; return ;; esac
    [ -f "$(_offsite_conf)" ] || { fail_pull "no offsite config"; return; }
    out="$(rclone --config "$(_offsite_conf)" ${_RCLONE_COMMON} \
            copy "offsite:${rpath}/${bucket}" "${bdir}/${bucket}" \
            --include "${ts}.*" 2>&1)" || { fail_pull "rclone copy failed (see backup.log)"; \
            printf '%s\n' "${out}" >> /var/log/backup.log; return; }
    printf '%s\n' "${out}" >> /var/log/backup.log 2>/dev/null || true
    n="$(ls "${bdir}/${bucket}/${ts}".* 2>/dev/null | wc -l | tr -d ' ')"
    if [ "${n}" = "0" ]; then
        fail_pull "no artefacts matched ${ts} on the remote"
        return
    fi
    printf '{"ok":true,"at":"%s","bucket":"%s","ts":"%s","files":%s}' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${bucket}" "${ts}" "${n}" \
        > "${bdir}/.offsite-pull-result" 2>/dev/null || true
    echo "[backup] offsite pull: ${bucket}/${ts} → local (${n} files)" | tee -a /var/log/backup.log
}

offsite_test() {
    # Connectivity probe: create the destination (mkdir also creates an S3
    # bucket) then list it. Writes ${BACKUP_DIR}/.offsite-test-result
    # {ok, at, path, error?}. Tighter timeouts than a push — this backs the
    # page's "Test connection" button.
    bdir="${BACKUP_DIR:-/backups}"
    rpath="$(_offsite_path)"
    if [ ! -f "$(_offsite_conf)" ]; then
        printf '{"ok":false,"at":"%s","path":"%s","error":"no offsite config"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${rpath}")" \
            > "${bdir}/.offsite-test-result" 2>/dev/null || true
        return
    fi
    out="$(rclone --config "$(_offsite_conf)" \
            --contimeout 10s --timeout 30s --retries 1 --low-level-retries 2 \
            mkdir "offsite:${rpath}" 2>&1 \
        && rclone --config "$(_offsite_conf)" \
            --contimeout 10s --timeout 30s --retries 1 --low-level-retries 2 \
            lsd "offsite:${rpath}" 2>&1)" && ok=1 || ok=0
    printf '%s\n' "${out}" >> /var/log/backup.log 2>/dev/null || true
    if [ "${ok}" = "1" ]; then
        printf '{"ok":true,"at":"%s","path":"%s"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${rpath}")" \
            > "${bdir}/.offsite-test-result" 2>/dev/null || true
        echo "[backup] offsite test: offsite:${rpath} reachable" | tee -a /var/log/backup.log
    else
        printf '{"ok":false,"at":"%s","path":"%s","error":"%s"}' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(_offsite_json_escape "${rpath}")" \
            "$(_offsite_json_escape "$(printf '%s' "${out}" | tail -n1)")" \
            > "${bdir}/.offsite-test-result" 2>/dev/null || true
        echo "[backup] offsite test: FAILED" | tee -a /var/log/backup.log
    fi
}
