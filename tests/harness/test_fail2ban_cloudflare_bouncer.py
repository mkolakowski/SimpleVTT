"""v2.472.0 — Phase 4d of
``docs/plans/fail2ban-crowdsec-integration.md``. Verifies the
Cloudflare bouncer ban action wiring.

Phase 4d ships an action.d/cloudflare-bouncer.conf that POSTs
banned IPs to the v2.430.0 Cloudflare access-rules API, plus the
``FAIL2BAN_ACTION`` env-var lever in the jail config that lets an
operator opt in via .env. This test asserts the contract:

- The action file exists and has both a POST (ban) and DELETE
  (unban) curl call.
- The action's [Init] block envsubst-resolves the v2.430.0
  CLOUDFLARE_* env vars.
- The reference jail's action= line is env-driven, not hardcoded.
- docker-compose passes FAIL2BAN_ACTION + every CLOUDFLARE_*
  through to the fail2ban service.
- render-jail.sh's allowlist covers the new placeholders so they
  get resolved at container start.
- The action.d template directory is mounted into the fail2ban
  service so render-jail.sh can read its source files.

Live-API integration testing (POST a synthetic ban, assert the
mock saw it) lands in Phase 4f's end-to-end smoke test where the
container's actually running.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_JAIL_CONFIG = _REPO_ROOT / "docs/integrations/fail2ban/jail.d/simplevtt.conf"
_ACTION_CONFIG = (
    _REPO_ROOT
    / "docs/integrations/fail2ban/action.d/cloudflare-bouncer.conf"
)
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"


def _load_compose() -> dict:
    with _COMPOSE.open() as f:
        return yaml.safe_load(f)


def _load_text(p: Path) -> str:
    return p.read_text()


def test_cloudflare_action_file_exists():
    """The action.d/cloudflare-bouncer.conf file ships alongside
    the existing reference configs."""
    assert _ACTION_CONFIG.is_file(), (
        f"cloudflare-bouncer action config missing at {_ACTION_CONFIG}"
    )


def test_cloudflare_action_has_post_ban_and_delete_unban():
    """The action file defines both an actionban (curl POST) and
    actionunban (curl DELETE) — fail2ban needs both for a clean
    ban-then-expire lifecycle."""
    text = _load_text(_ACTION_CONFIG)
    assert "actionban" in text, "action.d missing actionban definition"
    assert "actionunban" in text, "action.d missing actionunban definition"
    assert "curl" in text, "action body must invoke curl"
    assert "POST" in text, "actionban must POST"
    assert "DELETE" in text, "actionunban must DELETE"
    # The URL path is the Cloudflare access-rules API — same as the
    # v2.430.0 in-app integration uses.
    assert "firewall/access_rules/rules" in text


def test_cloudflare_action_init_uses_env_placeholders():
    """The action's [Init] block envsubst-resolves the v2.430.0
    CLOUDFLARE_* env vars so the resolved file has real values when
    fail2ban reads it."""
    text = _load_text(_ACTION_CONFIG)
    for placeholder in (
        "${CLOUDFLARE_API_TOKEN}",
        "${CLOUDFLARE_ZONE_ID}",
        "${CLOUDFLARE_API_BASE_URL}",
    ):
        assert placeholder in text, (
            f"action.d/cloudflare-bouncer.conf missing {placeholder} "
            "in [Init]"
        )


def test_jail_config_action_line_is_env_driven():
    """The jail config's action= line uses ${FAIL2BAN_ACTION}, not a
    hardcoded action shorthand. This is what lets an operator flip
    between bouncer actions via .env."""
    text = _load_text(_JAIL_CONFIG)
    # Find an uncommented `action = ...` line.
    action_line = None
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("action") and "=" in s:
            action_line = s
            break
    assert action_line is not None, (
        "jail config missing an uncommented action= line"
    )
    assert "${FAIL2BAN_ACTION}" in action_line, (
        f"jail action= line must use ${{FAIL2BAN_ACTION}} placeholder; "
        f"got {action_line!r}"
    )


def test_env_example_carries_fail2ban_action_default():
    """``.env.example`` has an uncommented FAIL2BAN_ACTION line so
    a fresh `.env` copy picks up the default."""
    text = _load_text(_ENV_EXAMPLE)
    found = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key = s.split("=", 1)[0]
        if key == "FAIL2BAN_ACTION":
            found = True
            break
    assert found, (
        ".env.example missing uncommented FAIL2BAN_ACTION default"
    )


def test_compose_passes_fail2ban_action_and_cloudflare_vars():
    """The compose fail2ban environment block plumbs FAIL2BAN_ACTION
    + all three CLOUDFLARE_* vars through. CLOUDFLARE_API_BASE_URL
    has a default value (Cloudflare public API) so unset envs still
    produce a working config — failed only on the missing token."""
    compose = _load_compose()
    env = compose["services"]["fail2ban"].get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    for v in (
        "FAIL2BAN_ACTION",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_API_BASE_URL",
    ):
        assert v in env, (
            f"fail2ban service env block missing {v}"
        )


def test_render_script_allowlist_includes_new_placeholders():
    """render-jail.sh's ``VARS`` allowlist must name the Phase 4d
    placeholders or they pass through to fail2ban literally and break
    the action. (v2.566.1: the v2.473.1 POSIX rewrite replaced
    envsubst's literal ``${VAR}`` markers with a bare-name allowlist —
    ``VARS='… CLOUDFLARE_API_TOKEN …'`` — so this asserts the bare
    names, matching the shipped script.)"""
    text = _load_text(_RENDER_SCRIPT)
    for v in (
        "FAIL2BAN_ACTION",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_API_BASE_URL",
    ):
        assert v in text, (
            f"render-jail.sh allowlist missing {v}"
        )


def test_compose_mounts_action_d_template():
    """The action.d/ directory is mounted as a read-only template
    into the fail2ban container so render-jail.sh can read its
    source files."""
    compose = _load_compose()
    volumes = compose["services"]["fail2ban"].get("volumes") or []
    mount = next(
        (v for v in volumes
         if isinstance(v, str)
         and "fail2ban/action.d:" in v
         and "action.d.template" in v),
        None,
    )
    assert mount is not None, (
        "fail2ban must mount docs/integrations/fail2ban/action.d at "
        "/etc/fail2ban/action.d.template; got volumes=" + str(volumes)
    )
    assert ":ro" in mount, (
        f"action.d template mount must be read-only; got {mount}"
    )
