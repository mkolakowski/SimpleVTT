"""v2.481.0 — Static config-shape validation for the
``simplevtt-flood`` fail2ban jail.

The jail bans IPs that fire a high volume of requests in a short
window (a scripted hammer the auth + scanner jails miss — those
only count failed logins / 404s). It consumes the opt-in
``visitor.request`` audit event (v2.480.0) and is itself gated OFF
by default (``FAIL2BAN_FLOOD_ENABLED=false``) so the two opt-ins
travel together.

This test set verifies the text-file contract that downstream
phases (render-jail.sh, the fail2ban container) depend on. It does
not depend on the fail2ban container being up.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_JAIL_CONFIG = _REPO_ROOT / "docs/integrations/fail2ban/jail.d/simplevtt.conf"
_FILTER_CONFIG = (
    _REPO_ROOT
    / "docs/integrations/fail2ban/filter.d/simplevtt-flood.conf"
)
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"

_PLACEHOLDERS = (
    "FAIL2BAN_FLOOD_ENABLED",
    "FAIL2BAN_FLOOD_MAXRETRY",
    "FAIL2BAN_FLOOD_FINDTIME",
    "FAIL2BAN_FLOOD_BANTIME",
)


def _load_compose() -> dict:
    with _COMPOSE.open() as f:
        return yaml.safe_load(f)


def _load_text(p: Path) -> str:
    return p.read_text()


def test_flood_filter_file_exists():
    """The filter.d/simplevtt-flood.conf file ships."""
    assert _FILTER_CONFIG.is_file(), (
        f"flood filter missing at {_FILTER_CONFIG}"
    )


def test_flood_filter_matches_visitor_request():
    """The failregex must reference the canonical ``visitor.request``
    event tag — without that, fail2ban tails the log and silently
    sees no matches."""
    text = _load_text(_FILTER_CONFIG)
    assert "visitor\\.request" in text or "visitor.request" in text, (
        "flood filter's failregex doesn't mention visitor.request; "
        "it'll never match the v2.480.0 audit-log lines"
    )
    assert "<HOST>" in text, (
        "flood filter must use the <HOST> placeholder so fail2ban "
        "can extract the IP to ban"
    )


def test_jail_config_includes_flood_block():
    """The jail.d config carries an uncommented ``[simplevtt-flood]``
    section with env-templated thresholds + the enabled gate."""
    text = _load_text(_JAIL_CONFIG)
    assert "[simplevtt-flood]" in text, (
        "jail.d/simplevtt.conf missing the [simplevtt-flood] block"
    )
    for placeholder in _PLACEHOLDERS:
        assert "${" + placeholder + "}" in text, (
            f"jail config missing ${{{placeholder}}}; render-jail.sh "
            "won't have a value to substitute"
        )


def test_flood_jail_enabled_is_env_gated():
    """The flood jail's ``enabled`` must be the env placeholder, NOT a
    hardcoded ``true`` — the jail only makes sense when per-request
    logging is on, so it ships OFF and the operator arms it
    explicitly."""
    text = _load_text(_JAIL_CONFIG)
    # Find the [simplevtt-flood] section body.
    after = text.split("[simplevtt-flood]", 1)[1]
    # Stop at the next section header if any.
    body = after.split("\n[", 1)[0]
    assert "enabled  = ${FAIL2BAN_FLOOD_ENABLED}" in body, (
        "flood jail's `enabled` must be env-gated via "
        "${FAIL2BAN_FLOOD_ENABLED}, not hardcoded true"
    )


def test_env_example_gates_flood_off_by_default():
    """``.env.example`` carries uncommented defaults for every
    FAIL2BAN_FLOOD_* var, and the enabled gate defaults to ``false``
    so ``cp .env.example .env`` leaves the flood jail disarmed."""
    text = _load_text(_ENV_EXAMPLE)
    found = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        if key in _PLACEHOLDERS:
            found[key] = val.strip()
    assert set(found) == set(_PLACEHOLDERS), (
        f".env.example missing one of FAIL2BAN_FLOOD_* defaults; "
        f"found {sorted(found)}"
    )
    assert found["FAIL2BAN_FLOOD_ENABLED"].lower() == "false", (
        "FAIL2BAN_FLOOD_ENABLED must default to false — the flood "
        f"jail ships disarmed; got {found['FAIL2BAN_FLOOD_ENABLED']!r}"
    )


def test_compose_passes_flood_env_vars():
    """The compose fail2ban service plumbs every FAIL2BAN_FLOOD_* env
    var through to the container, and the enabled gate defaults to
    false in the compose interpolation too."""
    compose = _load_compose()
    env = compose["services"]["fail2ban"].get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    for v in _PLACEHOLDERS:
        assert v in env, f"fail2ban service env block missing {v}"
    assert ":-false}" in str(env["FAIL2BAN_FLOOD_ENABLED"]), (
        "compose FAIL2BAN_FLOOD_ENABLED default must be false"
    )


def test_render_script_allowlist_includes_flood_placeholders():
    """render-jail.sh's allowlist covers the new placeholders so they
    get substituted at container start — including the enabled gate,
    which is NOT a threshold but still needs rendering."""
    text = _load_text(_RENDER_SCRIPT)
    for v in _PLACEHOLDERS:
        assert v in text, f"render-jail.sh allowlist missing {v}"
