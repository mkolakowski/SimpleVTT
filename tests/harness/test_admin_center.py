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
from pathlib import Path

import httpx
import pytest

from app.admin_center import (
    audit_parse,
    basic_auth,
    dns_lookup,
    event_help,
    fail2ban,
    fail2ban_control,
    login_guard,
    stats,
)

ADMIN_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")


def _admin_creds() -> tuple[str, str]:
    """The creds the *running* admin-center container uses. Read from
    the repo-root .env (the same file docker-compose reads) so a local
    operator who customized ADMIN_CENTER_USER/PASS still has passing
    tests; fall back to the compose defaults (what CI's credential-less
    stack uses). An explicit shell env var wins over both."""
    user, pw = "admin", "changeme"
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            s = line.strip()
            if s.startswith("ADMIN_CENTER_USER=") and "=" in s:
                user = s.split("=", 1)[1].strip() or user
            elif s.startswith("ADMIN_CENTER_PASS=") and "=" in s:
                pw = s.split("=", 1)[1].strip() or pw
    return os.getenv("ADMIN_CENTER_USER", user), os.getenv("ADMIN_CENTER_PASS", pw)


_ADMIN_USER, _ADMIN_PASS = _admin_creds()
_AUTH = httpx.BasicAuth(_ADMIN_USER, _ADMIN_PASS)

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


# ---- login brute-force guard ----------------------------------------

def test_login_guard_not_locked_under_threshold():
    store = {}
    for _ in range(4):
        login_guard.record_failure("1.2.3.4", now=1000.0, window_seconds=900, store=store)
    assert login_guard.lockout_remaining(
        "1.2.3.4", now=1000.0, max_attempts=5, window_seconds=900, store=store
    ) == 0


def test_login_guard_locks_at_threshold():
    store = {}
    for _ in range(5):
        login_guard.record_failure("1.2.3.4", now=1000.0, window_seconds=900, store=store)
    remaining = login_guard.lockout_remaining(
        "1.2.3.4", now=1000.0, max_attempts=5, window_seconds=900, store=store
    )
    assert remaining == 900  # full window left, oldest failure was just now


def test_login_guard_reset_clears():
    store = {}
    for _ in range(5):
        login_guard.record_failure("1.2.3.4", now=1000.0, window_seconds=900, store=store)
    login_guard.reset("1.2.3.4", store=store)
    assert login_guard.lockout_remaining(
        "1.2.3.4", now=1000.0, max_attempts=5, window_seconds=900, store=store
    ) == 0


def test_login_guard_window_expires_old_failures():
    store = {}
    for _ in range(5):
        login_guard.record_failure("1.2.3.4", now=1000.0, window_seconds=900, store=store)
    # 901s later the original failures have aged out of the window.
    assert login_guard.lockout_remaining(
        "1.2.3.4", now=1901.0, max_attempts=5, window_seconds=900, store=store
    ) == 0


def test_login_guard_is_per_ip():
    store = {}
    for _ in range(5):
        login_guard.record_failure("1.1.1.1", now=1000.0, window_seconds=900, store=store)
    # A different IP is unaffected.
    assert login_guard.lockout_remaining(
        "2.2.2.2", now=1000.0, max_attempts=5, window_seconds=900, store=store
    ) == 0


# ---- reverse-DNS lookup ---------------------------------------------

def test_dns_reverse_lookup_uses_cache():
    cache = {}
    calls = []

    def fake(ip, timeout):
        calls.append(ip)
        return "host.example.com"

    assert dns_lookup.reverse_lookup("1.2.3.4", resolver=fake, cache=cache) == "host.example.com"
    # Second call is served from cache — resolver not invoked again.
    assert dns_lookup.reverse_lookup("1.2.3.4", resolver=fake, cache=cache) == "host.example.com"
    assert calls == ["1.2.3.4"]


def test_dns_reverse_lookup_failure_caches_none():
    cache = {}

    def boom(ip, timeout):
        raise OSError("no PTR")

    assert dns_lookup.reverse_lookup("9.9.9.9", resolver=boom, cache=cache) is None
    assert cache["9.9.9.9"] is None


def test_dns_resolve_many_dedupes_skips_and_caps():
    cache = {}
    seen = []

    def fake(ip, timeout):
        seen.append(ip)
        return f"host-{ip}"

    out = dns_lookup.resolve_many(
        ["1.1.1.1", "1.1.1.1", "unknown", "", "2.2.2.2", "3.3.3.3"],
        limit=2, resolver=fake, cache=cache,
    )
    # Deduped + sentinels skipped; only 2 *new* lookups performed (cap).
    assert seen == ["1.1.1.1", "2.2.2.2"]
    assert out["1.1.1.1"] == "host-1.1.1.1"
    assert out["2.2.2.2"] == "host-2.2.2.2"
    assert out["3.3.3.3"] is None  # over the cap this render
    assert "unknown" not in out and "" not in out


# ---- fail2ban unban spool -------------------------------------------

def test_unban_request_writes_spool_file(tmp_path):
    res = fail2ban_control.request_unban("203.0.113.7", spool_dir=str(tmp_path))
    assert res["ok"] is True
    files = list(tmp_path.glob("unban-*.req"))
    assert len(files) == 1
    # The real IP is the file content (the watcher reads + re-sanitizes).
    assert files[0].read_text().strip() == "203.0.113.7"


def test_unban_request_accepts_ipv6(tmp_path):
    res = fail2ban_control.request_unban("2001:db8::5", spool_dir=str(tmp_path))
    assert res["ok"] is True
    assert list(tmp_path.glob("unban-*.req"))


def test_unban_request_rejects_invalid_ip(tmp_path):
    for bad in ("notanip", "999.999.1.1", "1.2.3.4; rm -rf /", ""):
        res = fail2ban_control.request_unban(bad, spool_dir=str(tmp_path))
        assert res["ok"] is False, bad
    # Nothing written for any rejected input.
    assert list(tmp_path.glob("*")) == []


def test_unban_request_filename_is_sanitized(tmp_path):
    # A hostile "IP" never reaches the filesystem (rejected as invalid),
    # but confirm the sanitizer keeps written names within the spool.
    fail2ban_control.request_unban("10.0.0.1", spool_dir=str(tmp_path))
    for f in tmp_path.glob("unban-*.req"):
        assert "/" not in f.name and ".." not in f.name


# ---- event help -----------------------------------------------------

def test_event_help_exact_match():
    assert "credential stuffing" in event_help.explain("auth.login_failed")
    assert "scanner" in event_help.explain("api.not_found").lower()


def test_event_help_prefix_fallback():
    # An admin.* tag with a suffix not individually listed falls back to
    # the admin family explanation.
    assert "admin" in event_help.explain("admin.user_delete").lower()
    assert "cloudflare" in event_help.explain("cloudflare.ban_ok").lower()


def test_event_help_generic_fallback():
    out = event_help.explain("totally.unknown")
    assert "audit event" in out.lower()


def test_event_help_empty():
    assert event_help.explain("") == event_help._GENERIC


def test_event_help_covers_every_signal_event():
    # Every named traffic-signal event has a real (non-generic)
    # explanation so the dashboard's signal cards all hover-explain.
    from app.admin_center.stats import _SIGNAL_EVENTS
    for tag in _SIGNAL_EVENTS:
        assert event_help.explain(tag) != event_help._GENERIC, tag


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
def test_unauthenticated_bounces_to_login_page_not_popup():
    """A browser navigation with no session is redirected to the login
    PAGE — and crucially never gets a WWW-Authenticate challenge (which
    is what triggers the native basic-auth popup)."""
    r = httpx.get(f"{ADMIN_BASE_URL}/", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")
    assert "www-authenticate" not in {k.lower() for k in r.headers}


@_LIVE
def test_login_page_renders():
    r = httpx.get(f"{ADMIN_BASE_URL}/login", timeout=5.0)
    assert r.status_code == 200
    assert "Sign in" in r.text
    assert 'name="password"' in r.text


@_LIVE
def test_login_flow_sets_session_and_grants_access():
    """POST valid creds → 303 + session cookie → dashboard renders."""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        r = c.post(
            "/login",
            data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/"},
        )
        assert r.status_code == 303
        assert "admin_center_session" in r.headers.get("set-cookie", "")
        # The cookie is now in the client jar — the dashboard loads.
        dash = c.get("/", follow_redirects=False)
        assert dash.status_code == 200
        assert "Admin Center" in dash.text
        assert "Log out" in dash.text


@_LIVE
def test_login_rejects_wrong_password():
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": "admin", "password": "nope", "next": "/"})
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
        assert "error" in r.headers.get("location", "")


@_LIVE
def test_logout_clears_session():
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        c.post("/login", data={
            "username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/",
        })
        assert c.get("/", follow_redirects=False).status_code == 200
        c.get("/logout")
        # After logout the dashboard bounces back to the login page.
        assert c.get("/", follow_redirects=False).status_code == 303


@_LIVE
def test_dashboard_renders_with_basic_auth_header():
    """Basic-auth header still works for scripts (no popup is ever
    challenged, but a supplied header is accepted)."""
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


@_LIVE
def test_dashboard_dns_toggle_renders_column():
    """With ?dns=1 the events table gains a Host (DNS) column."""
    r = httpx.get(f"{ADMIN_BASE_URL}/?dns=1", auth=_AUTH, timeout=15.0)
    assert r.status_code == 200
    assert "Host (DNS)" in r.text
    # Off by default — no column.
    r2 = httpx.get(f"{ADMIN_BASE_URL}/", auth=_AUTH, timeout=5.0)
    assert "Host (DNS)" not in r2.text


def _logged_in_client() -> httpx.Client:
    c = httpx.Client(base_url=ADMIN_BASE_URL, timeout=15.0, follow_redirects=False)
    c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/"})
    return c


@_LIVE
def test_unban_endpoint_accepts_valid_ip():
    c = _logged_in_client()
    try:
        r = c.post("/fail2ban/unban", data={"ip": "203.0.113.250"})
        assert r.status_code == 303
        assert "unbanned" in r.headers.get("location", "")
    finally:
        c.close()


@_LIVE
def test_unban_endpoint_rejects_invalid_ip():
    c = _logged_in_client()
    try:
        r = c.post("/fail2ban/unban", data={"ip": "not-an-ip"})
        assert r.status_code == 303
        assert "unban_error" in r.headers.get("location", "")
    finally:
        c.close()


@_LIVE
def test_unban_endpoint_requires_auth():
    # No session → the POST is bounced to the login page, not executed.
    r = httpx.post(
        f"{ADMIN_BASE_URL}/fail2ban/unban", data={"ip": "203.0.113.250"},
        timeout=5.0, follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


@_LIVE
def test_dashboard_renders_event_hover_help():
    """Each event row carries the hover-help affordance + tooltip."""
    r = httpx.get(f"{ADMIN_BASE_URL}/", auth=_AUTH, timeout=5.0)
    assert r.status_code == 200
    assert 'class="evt"' in r.text
    assert 'role="tooltip"' in r.text


@_LIVE
def test_api_events_dns_adds_ptr_field():
    r = httpx.get(f"{ADMIN_BASE_URL}/api/events?limit=5&dns=1", auth=_AUTH, timeout=15.0)
    assert r.status_code == 200
    events = r.json()["events"]
    if events:
        # ptr key present (value may be None for IPs with no PTR).
        assert "ptr" in events[0]
