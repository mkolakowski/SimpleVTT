"""v2.477.0 — Static config-shape validation for the
``simplevtt-scanner`` fail2ban jail.

The jail bans IPs that hit many distinct 404s in a short window
(vulnerability scanners probing /.env, /wp-admin, /phpinfo.php,
etc.). This test set verifies the YAML / text-file contract that
downstream phases (render-jail.sh, the fail2ban container, the
v2.477.0 audit event) depend on.

The live end-to-end test (fire 21 404s, poll
``fail2ban-client status simplevtt-scanner``, assert IP gets
banned) lives in ``test_fail2ban_end_to_end.py``. This file does
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
    / "docs/integrations/fail2ban/filter.d/simplevtt-scanner.conf"
)
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"


def _load_compose() -> dict:
    with _COMPOSE.open() as f:
        return yaml.safe_load(f)


def _load_text(p: Path) -> str:
    return p.read_text()


def test_scanner_filter_file_exists():
    """The filter.d/simplevtt-scanner.conf file ships."""
    assert _FILTER_CONFIG.is_file(), (
        f"scanner filter missing at {_FILTER_CONFIG}"
    )


def test_scanner_filter_matches_api_not_found():
    """The failregex must reference the canonical
    ``api.not_found`` event tag — without that, fail2ban tails
    the log and silently sees no matches."""
    text = _load_text(_FILTER_CONFIG)
    assert "api\\.not_found" in text or "api.not_found" in text, (
        "scanner filter's failregex doesn't mention api.not_found; "
        "it'll never match the v2.477.0 audit-log lines"
    )
    # The fail2ban <HOST> tag is how the engine extracts the IP.
    assert "<HOST>" in text, (
        "scanner filter must use the <HOST> placeholder so "
        "fail2ban can extract the IP to ban"
    )


def test_jail_config_includes_scanner_block():
    """The jail.d config carries an uncommented ``[simplevtt-scanner]``
    section with env-templated thresholds."""
    text = _load_text(_JAIL_CONFIG)
    assert "[simplevtt-scanner]" in text, (
        "jail.d/simplevtt.conf missing the [simplevtt-scanner] "
        "block"
    )
    # All three threshold placeholders must be present.
    for placeholder in (
        "${FAIL2BAN_SCANNER_MAXRETRY}",
        "${FAIL2BAN_SCANNER_FINDTIME}",
        "${FAIL2BAN_SCANNER_BANTIME}",
    ):
        assert placeholder in text, (
            f"jail config missing {placeholder}; render-jail.sh "
            "won't have a value to substitute"
        )


def test_env_example_carries_scanner_defaults():
    """The .env.example file carries uncommented defaults for the
    three FAIL2BAN_SCANNER_* env vars so ``cp .env.example .env``
    Just Works."""
    text = _load_text(_ENV_EXAMPLE)
    found = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key = s.split("=", 1)[0]
        if key in (
            "FAIL2BAN_SCANNER_MAXRETRY",
            "FAIL2BAN_SCANNER_FINDTIME",
            "FAIL2BAN_SCANNER_BANTIME",
        ):
            found.add(key)
    assert found == {
        "FAIL2BAN_SCANNER_MAXRETRY",
        "FAIL2BAN_SCANNER_FINDTIME",
        "FAIL2BAN_SCANNER_BANTIME",
    }, (
        f".env.example missing one of FAIL2BAN_SCANNER_* defaults; "
        f"found {sorted(found)}"
    )


def test_compose_passes_scanner_env_vars():
    """The compose fail2ban service plumbs every FAIL2BAN_SCANNER_*
    env var through to the container."""
    compose = _load_compose()
    env = compose["services"]["fail2ban"].get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    for v in (
        "FAIL2BAN_SCANNER_MAXRETRY",
        "FAIL2BAN_SCANNER_FINDTIME",
        "FAIL2BAN_SCANNER_BANTIME",
    ):
        assert v in env, (
            f"fail2ban service env block missing {v}"
        )


def test_render_script_allowlist_includes_scanner_placeholders():
    """render-jail.sh's allowlist covers the new placeholders so
    they get substituted at container start."""
    text = _load_text(_RENDER_SCRIPT)
    for v in (
        "FAIL2BAN_SCANNER_MAXRETRY",
        "FAIL2BAN_SCANNER_FINDTIME",
        "FAIL2BAN_SCANNER_BANTIME",
    ):
        assert v in text, (
            f"render-jail.sh allowlist missing {v}"
        )
