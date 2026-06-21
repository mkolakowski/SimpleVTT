"""Clear the audit log from the admin center.

The audit log is written by the *app* container's RotatingFileHandler
(append mode). The admin center shares the volume and runs as the same
``appuser`` uid, so it can truncate the file in place — keeping the
inode so the app's open handler keeps writing to the (now empty) file.
Rotated backups (``audit.log.1`` …) are removed for a clean slate.

A ``marker_line`` is appended after clearing so the clear is itself
auditable (who cleared it, when) — the canonical event tag
``admin_center.log_cleared`` matches no fail2ban filter, so it's inert
for banning.

Pure + stdlib-only so it's unit-testable against a temp dir.
"""
from __future__ import annotations

import glob
import os
from typing import Optional


def clear_audit_log(path: str, *, marker_line: Optional[str] = None) -> dict:
    """Truncate ``path`` to empty + remove its rotated backups.

    Returns ``{ok, cleared, backups_removed}`` or ``{ok: False, error}``.
    ``cleared`` is False when the file didn't exist (nothing to do, not
    an error). When ``marker_line`` is given it's appended after the
    truncate so the empty log opens with a record of the clear.
    """
    try:
        cleared = False
        if os.path.isfile(path):
            os.truncate(path, 0)
            cleared = True
        backups_removed = 0
        for bak in glob.glob(path + ".*"):
            try:
                os.remove(bak)
                backups_removed += 1
            except OSError:
                pass
        if marker_line:
            line = marker_line if marker_line.endswith("\n") else marker_line + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        return {"ok": True, "cleared": cleared, "backups_removed": backups_removed}
    except OSError as e:
        return {"ok": False, "error": str(e)}
