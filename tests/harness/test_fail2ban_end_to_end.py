"""v2.475.0 — Phase 4f of
``docs/plans/fail2ban-crowdsec-integration.md``. End-to-end smoke
test that verifies the v2.469.0–v2.473.1 wiring actually fires a
ban when a real attacker triggers the canonical events.

The test:
  1. Skips cleanly if the fail2ban container isn't running
     (``docker compose --profile fail2ban up -d`` is the prereq).
  2. Resets any prior bans on the simplevtt-auth jail.
  3. Replays N failed POST /login attempts (N > maxretry).
  4. Polls ``fail2ban-client status simplevtt-auth`` until the
     "Currently banned" count is non-zero, up to 30 s.
  5. Asserts the count > 0.

Why we don't set up + tear down the profile inside the test:
docker compose lifecycle from within pytest fights with the
operator/CI's compose state. Treating the profile as a precondition
(operator brings it up; the test reads from it) matches the
"Phase 2B gated" pattern the CrowdSec sibling uses.

Why we don't need to spoof X-Forwarded-For: the audit log
records WHATEVER IP the connection comes from. fail2ban just
needs to see N attempts from one IP in maxretry seconds. The
specific IP value doesn't matter — only the count.
"""
import re
import subprocess
import time

import httpx
import pytest

from .helpers import BASE_URL


def _fail2ban_container_running() -> bool:
    """Returns True iff `docker compose --profile fail2ban ps -q
    fail2ban` shows a running container ID."""
    try:
        r = subprocess.run(
            [
                "docker", "compose",
                "--profile", "fail2ban",
                "ps", "-q", "fail2ban",
            ],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def _fail2ban_client(*args, timeout: float = 10.0) -> subprocess.CompletedProcess:
    """Run a fail2ban-client command inside the fail2ban container.

    Returns the CompletedProcess; the caller inspects ``stdout`` /
    ``returncode``. Allows ``--all`` and other flags by passing
    them as positional args.
    """
    return subprocess.run(
        [
            "docker", "compose",
            "--profile", "fail2ban",
            "exec", "-T", "fail2ban",
            "fail2ban-client", *args,
        ],
        capture_output=True, text=True, timeout=timeout,
    )


def _currently_banned(status_output: str) -> int:
    """Parse the 'Currently banned: N' line out of
    ``fail2ban-client status simplevtt-auth`` output."""
    m = re.search(r"Currently banned:\s+(\d+)", status_output)
    return int(m.group(1)) if m else -1


async def test_failed_logins_trigger_fail2ban_ban():
    """6 failed logins from one IP → fail2ban-client reports the
    simplevtt-auth jail's banned-count > 0 within 30 s.

    This is the canonical end-to-end test for the v2.469.0–v2.473.1
    wiring: audit log emission → file handler → docker volume →
    fail2ban tail → filter match → ban decision. Skips if the
    fail2ban container isn't running.
    """
    if not _fail2ban_container_running():
        pytest.skip(
            "fail2ban container not running — run "
            "`docker compose --profile fail2ban up -d` first "
            "to enable this end-to-end test"
        )

    # Reset prior bans so the test is repeatable. Some images
    # spell the command `unban --all`; tolerate either error or
    # success since a fresh container has nothing to unban.
    _fail2ban_client("unban", "--all", timeout=5.0)

    # Fire enough failed logins to cross the default
    # FAIL2BAN_LOGIN_MAXRETRY=5 threshold. We send 6 with the
    # same bogus credentials in tight succession.
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        for _ in range(6):
            await client.post(
                "/login",
                data={
                    "email": "fail2ban-smoke-test@example.com",
                    "password": "definitely-wrong",
                },
            )

    # Poll fail2ban-client status until banned-count > 0 or
    # timeout. fail2ban's pyinotify backend usually reacts within
    # ~1 s of the log line landing.
    deadline = time.time() + 30
    banned_count = 0
    last_output = ""
    while time.time() < deadline:
        r = _fail2ban_client("status", "simplevtt-auth")
        last_output = r.stdout
        banned_count = _currently_banned(last_output)
        if banned_count > 0:
            break
        time.sleep(1)

    assert banned_count > 0, (
        "fail2ban didn't ban anyone after 6 failed logins within "
        "30 s. The v2.469.0–v2.473.1 wiring may have regressed "
        "(audit log → file handler → fail2ban tail → filter → "
        "ban decision). fail2ban-client status output:\n"
        f"{last_output}"
    )


async def test_jail_loaded_with_env_thresholds():
    """Sanity check: the jail is loaded with the env-derived
    thresholds from Phase 4c (FAIL2BAN_LOGIN_MAXRETRY=5,
    FAIL2BAN_LOGIN_FINDTIME=5m=300s, FAIL2BAN_LOGIN_BANTIME=1h=3600s).

    A drift between the .env-example defaults and what fail2ban
    actually loads means render-jail.sh broke or the env-var
    pass-through dropped a value."""
    if not _fail2ban_container_running():
        pytest.skip(
            "fail2ban container not running — run "
            "`docker compose --profile fail2ban up -d` first"
        )

    # Read the loaded jail config back from fail2ban-client.
    r = _fail2ban_client("status", "simplevtt-auth")
    assert r.returncode == 0, (
        f"fail2ban-client status simplevtt-auth failed: {r.stderr}"
    )
    # The status output doesn't show maxretry/findtime/bantime
    # directly; use `get` for each value.
    r_maxretry = _fail2ban_client("get", "simplevtt-auth", "maxretry")
    r_findtime = _fail2ban_client("get", "simplevtt-auth", "findtime")
    r_bantime = _fail2ban_client("get", "simplevtt-auth", "bantime")

    assert "5" in r_maxretry.stdout, (
        f"maxretry mismatch — expected 5, got {r_maxretry.stdout!r}"
    )
    assert "300" in r_findtime.stdout, (
        f"findtime mismatch — expected 300 (5m), got "
        f"{r_findtime.stdout!r}"
    )
    assert "3600" in r_bantime.stdout, (
        f"bantime mismatch — expected 3600 (1h), got "
        f"{r_bantime.stdout!r}"
    )
