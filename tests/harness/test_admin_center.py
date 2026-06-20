"""v2.483.0 — Admin Center: standalone read-only operator dashboard.

Three layers, mirroring the module split:

  * Pure unit tests (host-side, no container) for the audit-log
    parser, the stats roll-up, and the basic-auth credential check —
    all stdlib-only modules.
  * Live tests (httpx) against the admin-center service on port 8015
    for the basic-auth gate + the dashboard + the JSON APIs. They
    skip when the service isn't reachable (e.g. running the unit
    suite on a host without the stack up).
"""
import os
import sqlite3

import httpx
import pytest

from app.admin_center import audit_parse, basic_auth, fail2ban, stats

ADMIN_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")
_AUTH = httpx.BasicAuth(
    os.getenv("ADMIN_CENTER_USER", "admin"),
    os.getenv("ADMIN_CENTER_PASS", "changeme"),
)

_SAMPLE = """\
2026-06-20 01:00:00,001 WARNING simplevtt.audit: auth.login_failed ip=203.0.113.7 ua="Mozilla/5.0 (x)" username=alice@example.com
2026-06-20 01:00:01,002 WARNING simplevtt.audit: api.not_found ip=203.0.113.7 ua="scanner/1.0" path=/.env
2026-06-20 01:00:02,003 INFO simplevtt.audit: visitor.request ip=198.51.100.4 ua="curl/8" method=GET path="/a b" status=200 ms=5
2026-06-20 01:00:03,004 INFO simplevtt: SimpleVTT 2.483.0 starting...
not an audit line at all
"""


# ---- parser ---------------------------------------------------------

def test_parse_line_canonical_event():
    ev = audit_parse.parse_line(
        '2026-06-20 01:00:00,001 WARNING simplevtt.audit: auth.login_failed '
        'ip=203.0.113.7 ua="Mozilla/5.0 (x)" username=alice@example.com'
    )
    assert ev is not None
    assert ev["event"] == "auth.login_failed"
    assert ev["level"] == "WARNING"
    assert ev["fields"]["ip"] == "203.0.113.7"
    # Quoted value with whitespace is reassembled intact.
    assert ev["fields"]["ua"] == "Mozilla/5.0 (x)"
    assert ev["fields"]["username"] == "alice@example.com"


def test_parse_line_quoted_path_with_space():
    ev = audit_parse.parse_line(
        '2026-06-20 01:00:02,003 INFO simplevtt.audit: visitor.request '
        'ip=198.51.100.4 ua="curl/8" method=GET path="/a b" status=200 ms=5'
    )
    assert ev["fields"]["path"] == "/a b"
    assert ev["fields"]["status"] == "200"


def test_parse_line_rejects_non_audit_lines():
    assert audit_parse.parse_line(
        "2026-06-20 01:00:03,004 INFO simplevtt: SimpleVTT 2.483.0 starting..."
    ) is None
    assert audit_parse.parse_line("not an audit line at all") is None
    assert audit_parse.parse_line("") is None


def test_load_events_from_file(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text(_SAMPLE)
    events = audit_parse.load_events(str(p), newest_first=True)
    # 3 canonical events; the startup line + junk line are skipped.
    assert len(events) == 3
    # newest_first → the visitor.request is index 0.
    assert events[0]["event"] == "visitor.request"
    # prefix filter.
    auth_only = audit_parse.load_events(str(p), event_prefix="auth.")
    assert [e["event"] for e in auth_only] == ["auth.login_failed"]


def test_load_events_missing_file_is_empty():
    assert audit_parse.load_events("/no/such/audit.log") == []


# ---- stats ----------------------------------------------------------

def test_summarize_counts_and_top_lists(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text(_SAMPLE)
    events = audit_parse.load_events(str(p))
    s = stats.summarize(events)
    assert s["total_events"] == 3
    assert s["by_event"]["auth.login_failed"] == 1
    assert s["signals"]["Failed logins"] == 1
    assert s["signals"]["404 not found"] == 1
    assert s["signals"]["Visitor requests"] == 1
    # 203.0.113.7 appears twice → top IP.
    assert s["top_ips"][0] == ("203.0.113.7", 2)
    assert s["unique_ips"] == 2
    # path-bearing events feed top_paths.
    paths = dict(s["top_paths"])
    assert paths.get("/.env") == 1
    assert paths.get("/a b") == 1


# ---- fail2ban reader ------------------------------------------------

def _make_fail2ban_db(path, *, now):
    """Build a throwaway sqlite mirroring fail2ban's real schema and
    seed an active ban, an expired ban, and a permanent ban."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE jails(name TEXT NOT NULL PRIMARY KEY, enabled INTEGER)")
    conn.execute(
        "CREATE TABLE bips(ip TEXT NOT NULL, jail TEXT NOT NULL, "
        "timeofban INTEGER NOT NULL, bantime INTEGER NOT NULL, "
        "bancount INTEGER NOT NULL DEFAULT 1, data JSON, PRIMARY KEY(ip, jail))"
    )
    conn.execute(
        "CREATE TABLE bans(jail TEXT NOT NULL, ip TEXT, timeofban INTEGER NOT NULL, "
        "bantime INTEGER NOT NULL, bancount INTEGER NOT NULL DEFAULT 1, data JSON)"
    )
    conn.executemany(
        "INSERT INTO jails(name, enabled) VALUES (?, 1)",
        [("simplevtt-auth",), ("simplevtt-scanner",)],
    )
    conn.executemany(
        "INSERT INTO bips(ip, jail, timeofban, bantime, bancount) VALUES (?,?,?,?,?)",
        [
            ("203.0.113.7", "simplevtt-auth", int(now) - 100, 3600, 2),     # active
            ("198.51.100.9", "simplevtt-scanner", int(now) - 7200, 3600, 1),  # expired
            ("192.0.2.5", "simplevtt-auth", int(now) - 50, -1, 5),          # permanent
        ],
    )
    conn.executemany(
        "INSERT INTO bans(jail, ip, timeofban, bantime, bancount) VALUES (?,?,?,?,?)",
        [("simplevtt-auth", "203.0.113.7", int(now) - 100, 3600, 1)] * 4,
    )
    conn.commit()
    conn.close()


def test_fail2ban_missing_db_is_unavailable():
    s = fail2ban.read_status("/no/such/fail2ban.sqlite3", now=1000.0)
    assert s["available"] is False
    assert "fail2ban" in s["reason"].lower()
    assert s["banned"] == [] and s["total_current"] == 0


def test_fail2ban_reads_active_and_permanent_only(tmp_path):
    now = 1_700_000_000.0
    db = tmp_path / "fail2ban.sqlite3"
    _make_fail2ban_db(db, now=now)
    s = fail2ban.read_status(str(db), now=now)
    assert s["available"] is True
    # Active + permanent counted; expired excluded.
    assert s["total_current"] == 2
    ips = {b["ip"] for b in s["banned"]}
    assert ips == {"203.0.113.7", "192.0.2.5"}
    assert "198.51.100.9" not in ips
    # Permanent ban flagged.
    perm = next(b for b in s["banned"] if b["ip"] == "192.0.2.5")
    assert perm["permanent"] is True
    assert perm["remaining_seconds"] is None
    # Active ban has remaining time + carries bancount.
    active = next(b for b in s["banned"] if b["ip"] == "203.0.113.7")
    assert active["remaining_seconds"] == 3500
    assert active["bancount"] == 2
    # Historical count from the bans table + jail list.
    assert s["total_historical"] == 4
    assert s["jails"] == ["simplevtt-auth", "simplevtt-scanner"]
    assert s["by_jail"]["simplevtt-auth"] == 2


# ---- basic auth -----------------------------------------------------

def test_header_authorizes_valid(monkeypatch):
    monkeypatch.setenv("ADMIN_CENTER_USER", "admin")
    monkeypatch.setenv("ADMIN_CENTER_PASS", "s3cret")
    import base64
    token = base64.b64encode(b"admin:s3cret").decode()
    assert basic_auth.header_authorizes(f"Basic {token}") is True


def test_header_authorizes_rejects_bad(monkeypatch):
    monkeypatch.setenv("ADMIN_CENTER_USER", "admin")
    monkeypatch.setenv("ADMIN_CENTER_PASS", "s3cret")
    import base64
    bad = base64.b64encode(b"admin:wrong").decode()
    assert basic_auth.header_authorizes(f"Basic {bad}") is False
    assert basic_auth.header_authorizes(None) is False
    assert basic_auth.header_authorizes("Bearer xyz") is False
    assert basic_auth.header_authorizes("Basic !!!notb64!!!") is False


def test_is_default_password(monkeypatch):
    monkeypatch.setenv("ADMIN_CENTER_PASS", "changeme")
    assert basic_auth.is_default_password() is True
    monkeypatch.setenv("ADMIN_CENTER_PASS", "something-else")
    assert basic_auth.is_default_password() is False


# ---- live service (skips when not reachable) ------------------------

def _admin_up() -> bool:
    try:
        r = httpx.get(f"{ADMIN_BASE_URL}/healthz", timeout=3.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(
    not _admin_up(), reason="admin-center service not reachable on :8015"
)


@_LIVE
def test_healthz_open_without_auth():
    r = httpx.get(f"{ADMIN_BASE_URL}/healthz", timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "admin-center"


@_LIVE
def test_dashboard_requires_auth():
    r = httpx.get(f"{ADMIN_BASE_URL}/", timeout=5.0)
    assert r.status_code == 401
    assert "basic" in r.headers.get("www-authenticate", "").lower()


@_LIVE
def test_dashboard_rejects_wrong_creds():
    r = httpx.get(
        f"{ADMIN_BASE_URL}/", auth=httpx.BasicAuth("admin", "nope"), timeout=5.0,
    )
    assert r.status_code == 401


@_LIVE
def test_dashboard_renders_with_creds():
    r = httpx.get(f"{ADMIN_BASE_URL}/", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    assert "Admin Center" in r.text
    assert "Traffic signals" in r.text


@_LIVE
def test_api_stats_shape():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/stats", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    for key in ("total_events", "by_event", "signals", "top_ips", "top_paths"):
        assert key in body


@_LIVE
def test_api_events_shape():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/events?limit=10", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert "count" in body and "events" in body
    assert isinstance(body["events"], list)


@_LIVE
def test_api_events_requires_auth():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/events", timeout=5.0)
    assert r.status_code == 401


@_LIVE
def test_api_fail2ban_shape():
    """/api/fail2ban returns the ban-status envelope regardless of
    whether the fail2ban profile is running (available True or False
    both carry the same keys)."""
    r = httpx.get(f"{ADMIN_BASE_URL}/api/fail2ban", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    for key in ("available", "banned", "total_current", "total_historical", "jails", "by_jail"):
        assert key in body, f"fail2ban status missing {key!r}"
    assert isinstance(body["banned"], list)


@_LIVE
def test_api_fail2ban_requires_auth():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/fail2ban", timeout=5.0)
    assert r.status_code == 401


@_LIVE
def test_dashboard_shows_fail2ban_panel():
    r = httpx.get(f"{ADMIN_BASE_URL}/", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    assert "fail2ban" in r.text


@_LIVE
def test_api_inventory_shape():
    """/api/inventory returns DB row counts. The container has a
    database, so available is True and Users is a non-negative int."""
    r = httpx.get(f"{ADMIN_BASE_URL}/api/inventory", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert "available" in body and "counts" in body
    if body["available"]:
        assert "Users" in body["counts"]
        assert isinstance(body["counts"]["Users"], int)
        assert body["counts"]["Users"] >= 0


@_LIVE
def test_api_inventory_requires_auth():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/inventory", timeout=5.0)
    assert r.status_code == 401


@_LIVE
def test_dashboard_shows_data_inventory():
    r = httpx.get(f"{ADMIN_BASE_URL}/", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    assert "Data inventory" in r.text
