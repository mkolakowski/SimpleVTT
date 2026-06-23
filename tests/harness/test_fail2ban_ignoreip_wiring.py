"""v2.495.4 — fail2ban allowlist (``FAIL2BAN_IGNOREIP``) wiring.

Adds an env-driven ``ignoreip`` to the jails' ``[DEFAULT]`` block so an
operator can exempt a trusted source (e.g. a smoke-test / monitoring
host that runs the harness against the public deploy and would
otherwise self-ban on its own error-path 401/403/404 tests) without
editing the shipped config.

Mirrors ``test_fail2ban_env_threshold_wiring.py``: asserts the
placeholder is in the jail config's ``[DEFAULT] ignoreip`` line, the
render-jail.sh substitution allowlist carries it, docker-compose plumbs
it through, and ``.env.example`` documents a default.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_JAIL_CONFIG = _REPO_ROOT / "docs/integrations/fail2ban/jail.d/simplevtt.conf"
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"


def test_jail_default_block_has_ignoreip_placeholder():
    """The jail config carries a ``[DEFAULT]`` section whose
    ``ignoreip`` keeps localhost AND appends ${FAIL2BAN_IGNOREIP}, so
    the allowlist is inherited by every jail."""
    jail = _JAIL_CONFIG.read_text()
    assert "[DEFAULT]" in jail, "jail config missing a [DEFAULT] section"
    ignore_lines = [
        ln.strip() for ln in jail.splitlines()
        if ln.strip().startswith("ignoreip")
    ]
    assert ignore_lines, "jail config has no ignoreip line"
    line = ignore_lines[0]
    assert "${FAIL2BAN_IGNOREIP}" in line, (
        f"ignoreip must append the FAIL2BAN_IGNOREIP placeholder; got {line!r}"
    )
    # localhost must stay allowlisted regardless of the operator value.
    assert "127.0.0.1" in line, (
        f"ignoreip must keep localhost (127.0.0.1); got {line!r}"
    )


def test_jail_ignoreip_allowlists_cloudflare_ranges():
    """v2.599.0 — the published Cloudflare edge ranges are baked into the
    DEFAULT ignoreip so fail2ban never bans the Cloudflare edge (which,
    behind a CF Tunnel, is what gets attributed when CF-Connecting-IP is
    absent). 172.64.0.0/13 covers the 172.67.x edge that was self-banning."""
    jail = _JAIL_CONFIG.read_text()
    line = next(
        ln for ln in jail.splitlines() if ln.strip().startswith("ignoreip")
    )
    # A representative IPv4 + IPv6 CF range, incl. the 172.67.x block.
    for cidr in ("172.64.0.0/13", "104.16.0.0/13", "2400:cb00::/32", "2606:4700::/32"):
        assert cidr in line, f"ignoreip must allowlist Cloudflare {cidr}; got {line!r}"


def test_render_script_substitutes_ignoreip():
    """render-jail.sh's VARS allowlist includes FAIL2BAN_IGNOREIP so
    the placeholder is actually substituted at container start (an
    un-listed ${...} would pass through literally and break the jail)."""
    script = _RENDER_SCRIPT.read_text()
    vars_line = next(
        (ln for ln in script.splitlines() if ln.strip().startswith("VARS=")),
        "",
    )
    assert "FAIL2BAN_IGNOREIP" in vars_line, (
        "render-jail.sh VARS allowlist missing FAIL2BAN_IGNOREIP — the "
        "placeholder would render literally"
    )


def test_compose_passes_ignoreip_env():
    """The fail2ban service plumbs FAIL2BAN_IGNOREIP through from the
    host shell so .env can set it."""
    with _COMPOSE.open() as f:
        compose = yaml.safe_load(f)
    env = compose["services"]["fail2ban"].get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    assert "FAIL2BAN_IGNOREIP" in env, (
        "docker-compose fail2ban environment block missing FAIL2BAN_IGNOREIP"
    )


def test_env_example_documents_ignoreip():
    """.env.example carries a FAIL2BAN_IGNOREIP default (empty) so an
    operator copying it gets a defined, un-banning allowlist."""
    env_example = _ENV_EXAMPLE.read_text()
    found = any(
        ln.strip().split("=", 1)[0] == "FAIL2BAN_IGNOREIP"
        for ln in env_example.splitlines()
        if "=" in ln and not ln.strip().startswith("#")
    )
    assert found, "FAIL2BAN_IGNOREIP missing from .env.example"
