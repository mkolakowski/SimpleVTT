"""Write fail2ban unban requests to a shared control spool.

The admin center runs as the unprivileged ``appuser`` and the fail2ban
control socket is root-only (``srwx------``), so the dashboard can't
call ``fail2ban-client`` directly without breaking the v2.474.0
non-root hardening. Instead the unban button drops a request file into
a shared volume; a tiny watcher inside the (root) fail2ban container
(``scripts/unban-watcher.sh``) drains the spool and runs
``fail2ban-client unban <ip>``.

This module is the writer side: validate the IP, write a sanitized
request file. Pure enough to unit-test against a tmp dir (no web
stack, no fail2ban).
"""
from __future__ import annotations

import ipaddress
import os
import re

DEFAULT_CONTROL_DIR = "/data/control"


def control_dir() -> str:
    return os.environ.get("FAIL2BAN_CONTROL_DIR", DEFAULT_CONTROL_DIR)


def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def request_unban(ip: str, *, spool_dir: "str | None" = None) -> dict:
    """Queue an unban for ``ip``. Returns ``{ok, ...}``.

    Validates the IP (v4/v6) before writing — the watcher sanitizes
    again, but rejecting here gives the UI a clean 400. The request
    filename is derived from the IP (sanitized to ``[0-9a-fA-F]`` so it
    can't escape the spool dir); the real IP is the file *content*.
    """
    ip = (ip or "").strip()
    if not is_valid_ip(ip):
        return {"ok": False, "error": "invalid IP address"}
    spool = spool_dir or control_dir()
    try:
        os.makedirs(spool, exist_ok=True)
        safe = re.sub(r"[^0-9A-Fa-f]", "_", ip) or "x"
        path = os.path.join(spool, f"unban-{safe}.req")
        # Write atomically-ish: temp then rename so the watcher never
        # reads a half-written file.
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="ascii") as f:
            f.write(ip + "\n")
        os.replace(tmp, path)
        return {"ok": True, "ip": ip, "queued": path}
    except OSError as e:
        return {"ok": False, "error": f"could not write unban request: {e}"}
