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
    log_control,
    login_guard,
    mfa,
    operator_audit,
    stats,
    timefmt,
)

ADMIN_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")


def _env_file_value(key: str, default: str = "") -> str:
    """Read a value from the repo-root .env (the same file docker-compose
    reads) so tests match a locally-customized running stack; fall back
    to ``default`` (the compose default / what CI's stack uses). An
    explicit shell env var wins over both."""
    val = default
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            s = line.strip()
            if s.startswith(f"{key}=") and not s.startswith("#"):
                val = s.split("=", 1)[1].strip() or val
    return os.getenv(key, val)


def _admin_creds() -> tuple[str, str]:
    return (
        _env_file_value("ADMIN_CENTER_USER", "admin"),
        _env_file_value("ADMIN_CENTER_PASS", "changeme"),
    )


_ADMIN_USER, _ADMIN_PASS = _admin_creds()
_AUTH = httpx.BasicAuth(_ADMIN_USER, _ADMIN_PASS)
# If the running stack has MFA enabled (operator set it in .env), the
# login tests must complete the TOTP step. Empty = MFA off.
_MFA_SECRET = _env_file_value("ADMIN_CENTER_TOTP_SECRET", "")
_MFA_ON = (
    _env_file_value("ADMIN_CENTER_MFA_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    and bool(_MFA_SECRET)
)


def _complete_mfa_if_pending(client: httpx.Client, resp: httpx.Response) -> None:
    """If a password login redirected to the MFA step, finish it using
    the TOTP secret from .env so the helper works on an MFA-on stack."""
    if "/login/mfa" in resp.headers.get("location", "") and _MFA_SECRET:
        import time as _t

        from app.admin_center import mfa as _mfa
        code = _mfa._hotp(_MFA_SECRET, int(_t.time() // 30))
        client.post("/login/mfa", data={"code": code})

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


# ---- audit log clearing ---------------------------------------------

def test_clear_audit_log_truncates_and_marks(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text("old line 1\nold line 2\n")
    res = log_control.clear_audit_log(str(p), marker_line="MARKER cleared")
    assert res["ok"] is True
    assert res["cleared"] is True
    # Old content gone; only the marker remains.
    body = p.read_text()
    assert "old line" not in body
    assert body.strip() == "MARKER cleared"


def test_clear_audit_log_removes_rotated_backups(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text("x")
    (tmp_path / "audit.log.1").write_text("b1")
    (tmp_path / "audit.log.2").write_text("b2")
    res = log_control.clear_audit_log(str(p))
    assert res["ok"] is True
    assert res["backups_removed"] == 2
    assert not (tmp_path / "audit.log.1").exists()
    assert not (tmp_path / "audit.log.2").exists()


def test_clear_audit_log_missing_file_is_ok(tmp_path):
    res = log_control.clear_audit_log(str(tmp_path / "nope.log"))
    assert res["ok"] is True
    assert res["cleared"] is False


# ---- Cloudflare unban (edge rule removal) ---------------------------

async def test_cloudflare_unban_skips_when_not_configured(monkeypatch):
    from app.admin_center import cloudflare_unban
    from app.integrations import cloudflare
    monkeypatch.setattr(cloudflare, "integration_enabled", lambda: False)
    assert await cloudflare_unban.unban_ip("1.2.3.4") is None


async def test_cloudflare_unban_removes_only_matching_ban_rules(monkeypatch):
    from app.admin_center import cloudflare_unban
    from app.integrations import cloudflare

    rules = [
        {"id": "r1", "mode": "block", "configuration": {"target": "ip", "value": "1.2.3.4"}},
        {"id": "r2", "mode": "whitelist", "configuration": {"value": "1.2.3.4"}},   # skip (allow)
        {"id": "r3", "mode": "block", "configuration": {"value": "9.9.9.9"}},        # skip (other IP)
        {"id": "r4", "mode": "managed_challenge", "configuration": {"value": "1.2.3.4"}},  # remove
    ]
    removed = []

    async def fake_list(*, ip=None):
        return rules

    async def fake_remove(rule_id):
        removed.append(rule_id)

    monkeypatch.setattr(cloudflare, "integration_enabled", lambda: True)
    monkeypatch.setattr(cloudflare, "list_ip_access_rules", fake_list)
    monkeypatch.setattr(cloudflare, "remove_ip_access_rule", fake_remove)

    n = await cloudflare_unban.unban_ip("1.2.3.4")
    assert n == 2
    assert removed == ["r1", "r4"]


async def test_cloudflare_unban_graceful_on_api_error(monkeypatch):
    from app.admin_center import cloudflare_unban
    from app.integrations import cloudflare

    async def boom(*, ip=None):
        raise cloudflare.CloudflareApiError(500, "boom")

    monkeypatch.setattr(cloudflare, "integration_enabled", lambda: True)
    monkeypatch.setattr(cloudflare, "list_ip_access_rules", boom)
    # A Cloudflare hiccup must not raise — returns None, local unban still happened.
    assert await cloudflare_unban.unban_ip("1.2.3.4") is None


# ---- MFA: TOTP + recovery code --------------------------------------

# RFC 6238 test secret (ASCII "12345678901234567890") in base32. At
# T=59s (step 30 → counter 1) the 6-digit TOTP is 287082 — the same
# value Google Authenticator / Aegis / 1Password produce, so this
# pins our implementation to the real-world algorithm.
_RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def test_totp_matches_rfc6238_vector():
    assert mfa.verify_totp("287082", now=59, secret=_RFC_SECRET, valid_window=0) is True


def test_totp_rejects_wrong_code():
    assert mfa.verify_totp("000000", now=59, secret=_RFC_SECRET, valid_window=0) is False


def test_totp_window_tolerance():
    # A code valid at counter 1 (now=59) is accepted one step later
    # (now=89, counter 2) with valid_window=1...
    assert mfa.verify_totp("287082", now=89, secret=_RFC_SECRET, valid_window=1) is True
    # ...but not 3 steps away (counter 4).
    assert mfa.verify_totp("287082", now=149, secret=_RFC_SECRET, valid_window=1) is False


def test_totp_rejects_blank_and_nondigit():
    assert mfa.verify_totp("", now=59, secret=_RFC_SECRET) is False
    assert mfa.verify_totp("abcdef", now=59, secret=_RFC_SECRET) is False
    # No secret → always False.
    assert mfa.verify_totp("287082", now=59, secret="") is False


def test_recovery_blank_config_accepts_nothing():
    """The headline safety property: a blank recovery code rejects every
    submission, including a blank one — no empty==empty bypass."""
    mfa.reset_recovery_state()
    assert mfa.recovery_code_accepts("", configured="") is False
    assert mfa.recovery_code_accepts("anything", configured="") is False
    assert mfa.recovery_code_accepts("", configured="   ") is False


def test_recovery_set_matches_then_one_shot():
    mfa.reset_recovery_state()
    assert mfa.recovery_code_accepts("right-code", configured="right-code") is True
    assert mfa.recovery_code_accepts("wrong", configured="right-code") is False
    # One-shot: after consuming, even the correct code is refused.
    mfa.mark_recovery_used()
    assert mfa.recovery_code_accepts("right-code", configured="right-code") is False
    mfa.reset_recovery_state()
    assert mfa.recovery_code_accepts("right-code", configured="right-code") is True


def test_mfa_config_gates(monkeypatch):
    monkeypatch.delenv("ADMIN_CENTER_MFA_ENABLED", raising=False)
    assert mfa.mfa_enabled() is False
    monkeypatch.setenv("ADMIN_CENTER_MFA_ENABLED", "true")
    assert mfa.mfa_enabled() is True
    # Enabled but no secret → misconfigured (must fail closed).
    monkeypatch.delenv("ADMIN_CENTER_TOTP_SECRET", raising=False)
    assert mfa.totp_configured() is False
    assert mfa.mfa_misconfigured() is True
    monkeypatch.setenv("ADMIN_CENTER_TOTP_SECRET", _RFC_SECRET)
    assert mfa.totp_configured() is True
    assert mfa.mfa_misconfigured() is False


def test_provisioning_uri(monkeypatch):
    monkeypatch.setenv("ADMIN_CENTER_TOTP_SECRET", _RFC_SECRET)
    uri = mfa.provisioning_uri(account="admin")
    assert uri.startswith("otpauth://totp/")
    assert _RFC_SECRET in uri
    monkeypatch.delenv("ADMIN_CENTER_TOTP_SECRET", raising=False)
    assert mfa.provisioning_uri() == ""


# ---- operator audit (Phase 2 — Center-attributed mutations) ---------

def test_operator_audit_line_is_canonical_and_parseable():
    """A line the Center appends round-trips through the dashboard's own
    parser, with the operator attributed via actor=admin-center:<op>."""
    line = operator_audit.format_line(
        "admin.user_create", operator="admin",
        target="alice@example.com", ip="203.0.113.7", ua="curl/8",
        notes="display_name=Alice",
    )
    ev = audit_parse.parse_line(line)
    assert ev is not None
    assert ev["event"] == "admin.user_create"
    assert ev["level"] == "WARNING"  # mutations default to WARNING
    assert ev["fields"]["actor"] == "admin-center:admin"
    assert ev["fields"]["target"] == "alice@example.com"
    assert ev["fields"]["ip"] == "203.0.113.7"
    assert ev["fields"]["notes"] == "display_name=Alice"


def test_operator_audit_record_appends_parseable_line(tmp_path):
    p = tmp_path / "audit.log"
    p.write_text("")  # pre-existing (the app owns the real file)
    returned = operator_audit.record(
        "admin.user_delete", operator="op2",
        target="bob@example.com", path=str(p),
    )
    body = p.read_text().strip()
    assert body == returned
    ev = audit_parse.parse_line(body)
    assert ev["event"] == "admin.user_delete"
    assert ev["fields"]["actor"] == "admin-center:op2"


def test_operator_audit_record_no_path_returns_line_without_raising():
    # Stdout-only deploy: no AUDIT_LOG_PATH → returns the formatted line,
    # never raises (the mutation already happened).
    line = operator_audit.record(
        "admin.user_disable", operator="op", target="x@example.com", path="",
    )
    assert "admin.user_disable" in line
    assert "actor=admin-center:op" in line


# ---- user-admin service functions -----------------------------------

def test_user_admin_create_validates_and_rejects_duplicate():
    """Validation is exercised host-side against an in-memory sqlite so it
    needs no running container (skips on a host without the app deps)."""
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.admin_center import user_admin
    from app.models import Base, User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        u = user_admin.create_user(
            db, email="  NEW@Example.com ", display_name="", password="hunter2!!",
        )
        assert u.email == "new@example.com"
        # Blank display_name derives from the email local-part.
        assert u.display_name == "new"
        # Duplicate (case-insensitive) is rejected.
        with pytest.raises(user_admin.UserAdminError):
            user_admin.create_user(
                db, email="new@example.com", display_name="x", password="hunter2!!",
            )
        # Short password rejected.
        with pytest.raises(user_admin.UserAdminError):
            user_admin.create_user(
                db, email="b@example.com", display_name="b", password="short",
            )
        # Toggle disable + delete round-trip.
        _, disabled = user_admin.set_user_disabled(db, u.id)
        assert disabled is True
        email = user_admin.delete_user(db, u.id)
        assert email == "new@example.com"
        assert db.query(User).count() == 0
    finally:
        db.close()


# ---- campaign-admin service functions (Phase 3a) --------------------

def test_campaign_admin_list_detail_delete_roundtrip():
    """List → detail → delete exercised host-side against in-memory sqlite."""
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.admin_center import campaign_admin
    from app.models import Base, Campaign, User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        gm = User(email="gm@example.com", display_name="GM", password_hash="x")
        db.add(gm)
        db.commit()
        c = Campaign(name="Test Quest", gm_user_id=gm.id, game_system="dnd5e", description="")
        db.add(c)
        db.commit()
        rows = campaign_admin.list_campaigns(db)
        assert len(rows) == 1
        assert rows[0]["name"] == "Test Quest"
        assert rows[0]["gm_email"] == "gm@example.com"
        assert rows[0]["members"] == 0 and rows[0]["characters"] == 0 and rows[0]["maps"] == 0
        detail = campaign_admin.get_campaign_detail(db, c.id)
        assert detail["campaign"].name == "Test Quest"
        assert detail["gm_email"] == "gm@example.com"
        assert detail["members"] == [] and detail["characters"] == [] and detail["maps"] == []
        # Unknown id raises.
        with pytest.raises(campaign_admin.CampaignAdminError):
            campaign_admin.get_campaign_detail(db, 9999)
        # Delete returns the captured name; re-delete raises.
        name = campaign_admin.delete_campaign(db, c.id)
        assert name == "Test Quest"
        assert db.query(Campaign).count() == 0
        with pytest.raises(campaign_admin.CampaignAdminError):
            campaign_admin.delete_campaign(db, c.id)
    finally:
        db.close()


# ---- campaign-admin management mutations (Phase 3b) -----------------

def test_campaign_admin_member_system_character_mutations():
    """Member add/remove, system change, character create/assign/delete
    exercised host-side against in-memory sqlite."""
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.admin_center import campaign_admin
    from app.models import Base, Campaign, Character, CampaignMembership, User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        gm = User(email="gm@example.com", display_name="GM", password_hash="x")
        player = User(email="player@example.com", display_name="P", password_hash="x")
        db.add_all([gm, player])
        db.commit()
        c = Campaign(name="Quest", gm_user_id=gm.id, game_system="generic", description="")
        db.add(c)
        db.commit()
        # Member add → appears in detail's non_members shrinks; remove → gone.
        campaign_admin.add_member(db, c.id, user_id=player.id)
        assert db.query(CampaignMembership).filter_by(campaign_id=c.id, user_id=player.id).count() == 1
        # Idempotent add.
        campaign_admin.add_member(db, c.id, user_id=player.id)
        assert db.query(CampaignMembership).filter_by(campaign_id=c.id, user_id=player.id).count() == 1
        email = campaign_admin.remove_member(db, c.id, user_id=player.id)
        assert email == "player@example.com"
        assert db.query(CampaignMembership).filter_by(campaign_id=c.id, user_id=player.id).count() == 0
        # System change (normalized via get_system).
        key = campaign_admin.set_system(db, c.id, game_system="dnd5e")
        assert key == "dnd5e"
        # Character create → assign → delete.
        ch = campaign_admin.create_character(db, c.id, name="Bob", owner_user_id=None)
        assert ch.id and ch.campaign_id == c.id and ch.owner_user_id is None
        campaign_admin.assign_character(db, c.id, ch.id, owner_user_id=player.id)
        assert db.query(Character).get(ch.id).owner_user_id == player.id
        name = campaign_admin.delete_character(db, c.id, ch.id)
        assert name == "Bob"
        assert db.query(Character).count() == 0
        # Wrong-campaign / unknown guards.
        with pytest.raises(campaign_admin.CampaignAdminError):
            campaign_admin.delete_character(db, c.id, 9999)
        with pytest.raises(campaign_admin.CampaignAdminError):
            campaign_admin.add_member(db, c.id, user_id=9999)
    finally:
        db.close()


# ---- display timezone -----------------------------------------------

def test_timefmt_log_ts_converts_utc_to_offset():
    import calendar
    from datetime import timedelta, timezone
    est = timezone(timedelta(hours=-5))  # fixed offset, no tzdata needed
    # App logs UTC; 18:30 UTC → 13:30 at UTC-5.
    out = timefmt.fmt_log_ts("2026-01-15 18:30:00,123", tz=est)
    assert out.startswith("2026-01-15 13:30:00")


def test_timefmt_log_ts_passthrough_on_unparseable():
    assert timefmt.fmt_log_ts("not a timestamp") == "not a timestamp"
    assert timefmt.fmt_log_ts("") == ""


def test_timefmt_epoch_in_offset():
    import calendar
    from datetime import timedelta, timezone
    est = timezone(timedelta(hours=-5))
    ts = calendar.timegm((2026, 1, 15, 18, 0, 0, 0, 0, 0))  # 18:00 UTC
    assert timefmt.fmt_epoch(ts, tz=est).startswith("2026-01-15 13:00")
    assert timefmt.fmt_epoch(0) == "" or timefmt.fmt_epoch(None) == ""


def test_timefmt_display_tz_name_default_and_override(monkeypatch):
    monkeypatch.delenv("ADMIN_CENTER_TZ", raising=False)
    assert timefmt.display_tz_name() == "America/New_York"
    monkeypatch.setenv("ADMIN_CENTER_TZ", "UTC")
    assert timefmt.display_tz_name() == "UTC"


def test_timefmt_display_tz_falls_back_on_bad_name(monkeypatch):
    from datetime import timezone
    monkeypatch.setenv("ADMIN_CENTER_TZ", "Not/AZone")
    assert timefmt.display_tz() == timezone.utc


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
def test_favicon_served_without_auth():
    """The admin center serves the same favicon as the main site, and
    it's reachable without logging in (so the login page shows it)."""
    r = httpx.get(f"{ADMIN_BASE_URL}/favicon.svg", timeout=5.0, follow_redirects=False)
    assert r.status_code == 200
    assert "svg" in r.headers.get("content-type", "").lower()
    # Same bytes as the main app's /static/favicon.svg.
    main = httpx.get("http://localhost:8013/static/favicon.svg", timeout=5.0)
    if main.status_code == 200:
        assert r.content == main.content


@_LIVE
def test_login_page_references_favicon():
    r = httpx.get(f"{ADMIN_BASE_URL}/login", timeout=5.0)
    assert r.status_code == 200
    assert '/favicon.svg' in r.text


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
        # On an MFA-on stack the password step lands on /login/mfa;
        # complete the second factor before checking the dashboard.
        _complete_mfa_if_pending(c, r)
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
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=10.0, follow_redirects=False) as c:
        r = c.post("/login", data={
            "username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/",
        })
        _complete_mfa_if_pending(c, r)  # finish TOTP if MFA is on
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
    r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/"})
    _complete_mfa_if_pending(c, r)  # finishes the TOTP step if MFA is on
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
def test_mfa_step_requires_pending_session():
    """GET /login/mfa without a mid-login (mfa_pending) session bounces
    to /login — you can't jump straight to the second-factor step."""
    r = httpx.get(f"{ADMIN_BASE_URL}/login/mfa", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


@_LIVE
@pytest.mark.skipif(_MFA_ON, reason="stack has MFA enabled — password alone won't grant")
def test_mfa_disabled_login_still_grants_directly():
    """With MFA off (the default), a valid password lands straight on
    the dashboard — no /login/mfa detour. Skipped on an MFA-on stack."""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=10.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/"})
        # Password alone authenticated (no MFA redirect).
        assert "/login/mfa" not in r.headers.get("location", "")
        dash = c.get("/", follow_redirects=False)
        assert dash.status_code == 200
        assert "Admin Center" in dash.text


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
def test_logs_clear_requires_auth():
    # No session → bounced to /login WITHOUT clearing the log (the auth
    # gate runs before the handler). We deliberately don't test the
    # happy path live — it would wipe the shared container's audit log.
    r = httpx.post(
        f"{ADMIN_BASE_URL}/logs/clear", timeout=5.0, follow_redirects=False,
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


# ---- /tests dashboard (v2.573.0) ------------------------------------------
@_LIVE
def test_tests_page_redirects_when_unauthenticated():
    """The /tests dashboard is auth-gated like the rest of the center —
    a no-session navigation bounces to the login page, no basic-auth popup."""
    r = httpx.get(f"{ADMIN_BASE_URL}/tests", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")
    assert "www-authenticate" not in {k.lower() for k in r.headers}


@_LIVE
def test_tests_page_renders_authenticated():
    """After session login, /tests renders the harness test-results
    dashboard (heading + nav back to the dashboard). It shows either the
    latest run or the documented empty-state — both are a valid 200."""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        r = c.post(
            "/login",
            data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/tests"},
        )
        assert r.status_code == 303
        _complete_mfa_if_pending(c, r)
        page = c.get("/tests", follow_redirects=False)
        assert page.status_code == 200, page.text[:200]
        assert "Test results" in page.text
        assert 'href="/"' in page.text  # back-to-dashboard link
        # Either a run summary or the empty-state — never a server error.
        assert ("Latest run" in page.text) or ("No test runs yet" in page.text)


# ---- /tools admin-tools page (v2.573.2) -----------------------------------
@_LIVE
def test_tools_page_redirects_when_unauthenticated():
    """The /tools surface is auth-gated like the rest of the center."""
    r = httpx.get(f"{ADMIN_BASE_URL}/tools", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")


@_LIVE
def test_tools_page_renders_when_enabled():
    """With ADMIN_CENTER_ADMIN_TOOLS=true (set in the test env), the page
    renders the operator tools. (If the flag is off this stack returns 404 —
    handle both so the suite is portable across configs.)"""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/tools"})
        assert r.status_code == 303
        _complete_mfa_if_pending(c, r)
        page = c.get("/tools", follow_redirects=False)
        if page.status_code == 404:
            assert "Admin tools are disabled" in page.text  # flag off
            return
        assert page.status_code == 200, page.text[:200]
        assert "Admin tools" in page.text
        assert 'action="/tools/demo/reset"' in page.text or "DEMO_MODE" in page.text


@_LIVE
def test_tools_mint_magic_link():
    """Minting a demo magic link (non-destructive) → 303 back to /tools with
    the minted URL. Skips cleanly if admin-tools or magic-link is off."""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=8.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/tools"})
        _complete_mfa_if_pending(c, r)
        if c.get("/tools", follow_redirects=False).status_code == 404:
            pytest.skip("admin tools disabled on this stack")
        m = c.post("/tools/demo/mint-magic-link",
                   data={"sub": "demo-gm@example.com"}, follow_redirects=False)
        assert m.status_code == 303, m.text[:200]
        loc = m.headers.get("location", "")
        # Either a minted link or a clean error (e.g. magic-link disabled).
        assert "minted=" in loc or "err=" in loc


@_LIVE
def test_tools_demo_reset_requires_auth():
    """The DESTRUCTIVE demo-reset is auth-gated — an unauthenticated POST is
    bounced to login and never fires the reseed. (We never POST it
    authenticated in tests; that would wipe the demo data.)"""
    r = httpx.post(f"{ADMIN_BASE_URL}/tools/demo/reset", timeout=5.0, follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


# ---- /users user-admin page (v2.574.0, Phase 2a) --------------------------
@_LIVE
def test_users_page_redirects_when_unauthenticated():
    """The /users surface is auth-gated like the rest of the center."""
    r = httpx.get(f"{ADMIN_BASE_URL}/users", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")
    assert "www-authenticate" not in {k.lower() for k in r.headers}


def _tools_enabled(c: httpx.Client) -> bool:
    """True iff ADMIN_CENTER_ADMIN_TOOLS is on (the surface returns 404 when
    off). Assumes the client is already logged in."""
    return c.get("/users", follow_redirects=False).status_code != 404


@_LIVE
def test_users_page_renders_when_enabled():
    """With ADMIN_CENTER_ADMIN_TOOLS=true the page lists users + the create
    form. (If the flag is off this stack returns 404 — handle both so the
    suite is portable across configs.)"""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=5.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/users"})
        assert r.status_code == 303
        _complete_mfa_if_pending(c, r)
        page = c.get("/users", follow_redirects=False)
        if page.status_code == 404:
            assert "Admin tools are disabled" in page.text  # flag off
            return
        assert page.status_code == 200, page.text[:200]
        assert "User admin" in page.text
        assert 'action="/users/create"' in page.text


@_LIVE
def test_users_create_rejects_duplicate_email():
    """Creating a user with an already-used email redirects back with an
    error banner (no duplicate row). Uses the seeded admin's own email,
    which always exists, so the duplicate path is deterministic without
    leaving a new row behind. Skips when admin-tools is off."""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=8.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/users"})
        _complete_mfa_if_pending(c, r)
        if not _tools_enabled(c):
            pytest.skip("admin tools disabled on this stack")
        # Look up an existing email from the rendered table to force the
        # duplicate path without inventing+leaving a new account.
        import re as _re
        page = c.get("/users", follow_redirects=False)
        m = _re.search(r"<td>([^<@]+@[^<]+)</td>", page.text)
        if not m:
            pytest.skip("no existing user to duplicate")
        existing = m.group(1).strip()
        resp = c.post(
            "/users/create",
            data={"email": existing, "display_name": "dupe", "password": "hunter2!!"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "err=" in resp.headers.get("location", "")


@_LIVE
def test_users_create_requires_auth():
    """An unauthenticated create POST is bounced to login, never creating."""
    r = httpx.post(
        f"{ADMIN_BASE_URL}/users/create",
        data={"email": "x@example.com", "display_name": "x", "password": "hunter2!!"},
        timeout=5.0, follow_redirects=False,
    )
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


# ---- /users destructive ops (v2.575.0, Phase 2b — MFA-gated) --------------
@_LIVE
@pytest.mark.parametrize("path", ["/users/1/disable", "/users/1/delete", "/users/1/reset-password"])
def test_users_destructive_requires_auth(path):
    """Unauthenticated destructive POSTs are bounced to login, never run."""
    r = httpx.post(f"{ADMIN_BASE_URL}{path}", timeout=5.0, follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


@_LIVE
@pytest.mark.parametrize("path", ["/users/1/disable", "/users/1/delete"])
def test_users_destructive_refused_for_header_auth(path):
    """The MFA gate: a basic-auth *header* caller has no MFA-verified login
    session, so destructive ops are refused — 403 (gated) when admin-tools
    are on, or 404 when the surface is off. Either way the op never runs.
    Deterministic regardless of whether the stack has MFA enabled."""
    r = httpx.post(f"{ADMIN_BASE_URL}{path}", auth=_AUTH, timeout=5.0, follow_redirects=False)
    assert r.status_code in (403, 404), r.text[:200]


@_LIVE
@pytest.mark.skipif(not _MFA_ON, reason="destructive ops need an MFA-verified session; stack has MFA off")
def test_users_disable_reset_delete_roundtrip():
    """Full destructive happy path on an MFA-on stack, using a throwaway
    account so no real demo user is touched: create → disable → re-enable →
    reset-password → delete → re-delete (error, already gone)."""
    c = _logged_in_client()
    try:
        if not _tools_enabled(c):
            pytest.skip("admin tools disabled on this stack")
        import re as _re
        email = "phase2b-throwaway@example.com"
        # Clean any leftover from a prior aborted run, then create fresh.
        page = c.get("/users", follow_redirects=False).text
        m = _re.search(r"<td>(\d+)</td>\s*<td>" + _re.escape(email) + r"</td>", page)
        if m:
            c.post(f"/users/{m.group(1)}/delete", follow_redirects=False)
        made = c.post("/users/create", data={
            "email": email, "display_name": "Throwaway", "password": "hunter2!!",
        }, follow_redirects=False)
        assert made.status_code == 303 and "created=" in made.headers.get("location", "")
        page = c.get("/users", follow_redirects=False).text
        m = _re.search(r"<td>(\d+)</td>\s*<td>" + _re.escape(email) + r"</td>", page)
        assert m, "throwaway user not listed after create"
        uid = m.group(1)
        # Disable → the row gains the 'disabled' pill.
        d = c.post(f"/users/{uid}/disable", follow_redirects=False)
        assert d.status_code == 303 and "done=" in d.headers.get("location", "")
        # Re-enable.
        c.post(f"/users/{uid}/disable", follow_redirects=False)
        # Reset password (never logs the plaintext).
        rp = c.post(f"/users/{uid}/reset-password",
                    data={"new_password": "newpass99"}, follow_redirects=False)
        assert rp.status_code == 303 and "done=" in rp.headers.get("location", "")
        # Delete → done; deleting again errors (already gone).
        de = c.post(f"/users/{uid}/delete", follow_redirects=False)
        assert de.status_code == 303 and "done=" in de.headers.get("location", "")
        again = c.post(f"/users/{uid}/delete", follow_redirects=False)
        assert again.status_code == 303 and "err=" in again.headers.get("location", "")
    finally:
        c.close()


# ---- /campaigns campaign-admin page (v2.576.0, Phase 3a) ------------------
@_LIVE
def test_campaigns_page_redirects_when_unauthenticated():
    """The /campaigns surface is auth-gated like the rest of the center."""
    r = httpx.get(f"{ADMIN_BASE_URL}/campaigns", timeout=5.0, follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers.get("location", "")
    assert "www-authenticate" not in {k.lower() for k in r.headers}


@_LIVE
def test_campaigns_page_renders_when_enabled():
    """With ADMIN_CENTER_ADMIN_TOOLS=true the page lists campaigns; a detail
    link drills into a read-only view. (404 when the flag is off.)"""
    with httpx.Client(base_url=ADMIN_BASE_URL, timeout=8.0, follow_redirects=False) as c:
        r = c.post("/login", data={"username": _ADMIN_USER, "password": _ADMIN_PASS, "next": "/campaigns"})
        assert r.status_code == 303
        _complete_mfa_if_pending(c, r)
        page = c.get("/campaigns", follow_redirects=False)
        if page.status_code == 404:
            assert "Admin tools are disabled" in page.text  # flag off
            return
        assert page.status_code == 200, page.text[:200]
        assert "Campaign admin" in page.text
        # Drill into the first campaign, if any, and confirm the read-only
        # detail renders its sections.
        import re as _re
        m = _re.search(r'href="/campaigns/(\d+)"', page.text)
        if m:
            detail = c.get(f"/campaigns/{m.group(1)}", follow_redirects=False)
            assert detail.status_code == 200, detail.text[:200]
            assert "Overview" in detail.text and "Members" in detail.text


@_LIVE
def test_campaign_detail_unknown_redirects_with_error():
    """An unknown campaign id redirects back to the list with an error
    (no 500). Skips when admin-tools is off."""
    c = _logged_in_client()
    try:
        if c.get("/campaigns", follow_redirects=False).status_code == 404:
            pytest.skip("admin tools disabled on this stack")
        r = c.get("/campaigns/99999999", follow_redirects=False)
        assert r.status_code == 303
        assert "/campaigns" in r.headers.get("location", "") and "err=" in r.headers.get("location", "")
    finally:
        c.close()


@_LIVE
def test_campaign_delete_requires_auth():
    """An unauthenticated delete POST is bounced to login, never deleting."""
    r = httpx.post(f"{ADMIN_BASE_URL}/campaigns/1/delete", timeout=5.0, follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


@_LIVE
def test_campaign_delete_refused_for_header_auth():
    """The MFA gate: a basic-auth header caller has no MFA-verified session,
    so campaign-delete is refused — 403 (gated) or 404 (surface off). We
    deliberately never POST it from an MFA-verified session in tests (that
    would wipe a real demo campaign)."""
    r = httpx.post(f"{ADMIN_BASE_URL}/campaigns/1/delete", auth=_AUTH, timeout=5.0, follow_redirects=False)
    assert r.status_code in (403, 404), r.text[:200]


# ---- /campaigns management mutations (v2.577.0, Phase 3b) -----------------
_CAMPAIGN_MUTATIONS = [
    "/campaigns/1/members/add",
    "/campaigns/1/members/remove",
    "/campaigns/1/system",
    "/campaigns/1/characters/create",
    "/campaigns/1/characters/1/assign",
    "/campaigns/1/characters/1/delete",
]


@_LIVE
@pytest.mark.parametrize("path", _CAMPAIGN_MUTATIONS)
def test_campaign_mutations_require_auth(path):
    """Unauthenticated management POSTs are bounced to login, never run."""
    r = httpx.post(f"{ADMIN_BASE_URL}{path}", timeout=5.0, follow_redirects=False)
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


@_LIVE
@pytest.mark.parametrize("path", ["/campaigns/1/members/remove", "/campaigns/1/characters/1/delete", "/campaigns/1/system"])
def test_campaign_mutations_refused_for_header_auth(path):
    """The MFA gate: a basic-auth header caller is never MFA-verified, so the
    management mutations are refused — 403 (gated) or 404 (surface off)."""
    r = httpx.post(f"{ADMIN_BASE_URL}{path}", auth=_AUTH, timeout=5.0,
                   data={"user_id": "1", "game_system": "generic"}, follow_redirects=False)
    assert r.status_code in (403, 404), r.text[:200]


@_LIVE
@pytest.mark.skipif(not _MFA_ON, reason="campaign mutations need an MFA-verified session; stack has MFA off")
def test_campaign_character_create_assign_delete_roundtrip():
    """Net-zero character round-trip on a real campaign (create → assign →
    delete) on an MFA-on stack — no demo data is left changed. Skips when
    admin-tools is off or there are no campaigns."""
    import re as _re
    c = _logged_in_client()
    try:
        lst = c.get("/campaigns", follow_redirects=False)
        if lst.status_code == 404:
            pytest.skip("admin tools disabled on this stack")
        m = _re.search(r'href="/campaigns/(\d+)"', lst.text)
        if not m:
            pytest.skip("no campaigns to manage")
        cid = m.group(1)
        made = c.post(f"/campaigns/{cid}/characters/create",
                      data={"name": "phase3b-throwaway", "owner_user_id": ""},
                      follow_redirects=False)
        assert made.status_code == 303 and "done=" in made.headers.get("location", "")
        detail = c.get(f"/campaigns/{cid}", follow_redirects=False).text
        ch = _re.search(r"<td>(\d+)</td><td>phase3b-throwaway</td>", detail)
        assert ch, "throwaway character not listed after create"
        chid = ch.group(1)
        # Assign to an arbitrary existing user, then delete (net-zero).
        uid = _re.search(r'name="owner_user_id">\s*<option value="">[^<]*</option>\s*<option value="(\d+)"', detail)
        if uid:
            a = c.post(f"/campaigns/{cid}/characters/{chid}/assign",
                       data={"owner_user_id": uid.group(1)}, follow_redirects=False)
            assert a.status_code == 303 and "done=" in a.headers.get("location", "")
        d = c.post(f"/campaigns/{cid}/characters/{chid}/delete", follow_redirects=False)
        assert d.status_code == 303 and "done=" in d.headers.get("location", "")
    finally:
        c.close()
