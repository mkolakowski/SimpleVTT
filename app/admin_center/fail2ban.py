"""Read fail2ban ban state directly from its sqlite database.

The crazymax/fail2ban image persists state to a sqlite db (its
``dbfile`` is ``/data/db/fail2ban.sqlite3``). The admin-center service
mounts that volume **read-only** and reads the ``bips`` table — the
set of currently-banned IPs — without needing ``fail2ban-client`` or
a shared control socket.

Schema (fail2ban 1.x):
  * ``bips(ip, jail, timeofban, bantime, bancount, data)`` — the
    *currently* banned IPs. fail2ban deletes a row on unban; a row
    whose ``timeofban + bantime`` is in the past is expired-but-not-
    yet-purged, so we filter those out. ``bantime < 0`` is a
    permanent ban.
  * ``bans(...)`` — full historical ban log (count only).
  * ``jails(name)`` — configured jails.

Pure + stdlib-only so it's unit-testable against a throwaway sqlite
file without the web stack.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = "/data/db/fail2ban.sqlite3"


def _connect_ro(db_path: str) -> sqlite3.Connection:
    # mode=ro respects fail2ban's journal so we see committed state
    # without taking a write lock. A short timeout + graceful error
    # handling covers the rare "database is locked" window.
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)


def read_status(db_path: Optional[str] = None, *, now: float) -> dict:
    """Return fail2ban ban state as a dict.

    ``available`` is False (with a human ``reason``) when the db is
    missing or unreadable — e.g. the ``--profile fail2ban`` service
    isn't running, so the shared volume has no db yet. The dashboard
    renders that as an empty state rather than an error.
    """
    db_path = db_path or os.environ.get("FAIL2BAN_DB_PATH", DEFAULT_DB_PATH)

    if not os.path.isfile(db_path):
        return {
            "available": False,
            "db_path": db_path,
            "reason": (
                "No fail2ban database found. Bring up the banning stack "
                "with `docker compose --profile fail2ban up -d`."
            ),
            "jails": [],
            "banned": [],
            "total_current": 0,
            "total_historical": 0,
            "by_jail": {},
        }

    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error as e:  # pragma: no cover - defensive
        return {
            "available": False,
            "db_path": db_path,
            "reason": f"Could not open ban database: {e}",
            "jails": [], "banned": [], "total_current": 0,
            "total_historical": 0, "by_jail": {},
        }

    try:
        cur = conn.cursor()
        jails = [r[0] for r in cur.execute("SELECT name FROM jails ORDER BY name")]
        rows = cur.execute(
            "SELECT ip, jail, timeofban, bantime, bancount "
            "FROM bips ORDER BY timeofban DESC"
        ).fetchall()
        historical = cur.execute("SELECT COUNT(*) FROM bans").fetchone()[0]
    except sqlite3.Error as e:
        return {
            "available": False,
            "db_path": db_path,
            "reason": f"Ban database query failed: {e}",
            "jails": [], "banned": [], "total_current": 0,
            "total_historical": 0, "by_jail": {},
        }
    finally:
        conn.close()

    banned = []
    by_jail: dict[str, int] = {}
    for ip, jail, timeofban, bantime, bancount in rows:
        permanent = bantime is not None and bantime < 0
        expires_at = None if permanent else (timeofban + bantime)
        active = permanent or (expires_at is not None and expires_at > now)
        if not active:
            continue
        banned.append({
            "ip": ip,
            "jail": jail,
            "banned_at": timeofban,
            "ban_seconds": bantime,
            "expires_at": expires_at,
            "permanent": permanent,
            "bancount": bancount,
            "remaining_seconds": None if permanent else int(expires_at - now),
        })
        by_jail[jail] = by_jail.get(jail, 0) + 1

    return {
        "available": True,
        "db_path": db_path,
        "jails": jails,
        "banned": banned,
        "total_current": len(banned),
        "total_historical": int(historical),
        "by_jail": by_jail,
    }
