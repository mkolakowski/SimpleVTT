"""v2.566.0 — optional Discord webhook notification action for the
fail2ban integration (``docs/plans/fail2ban-crowdsec-integration.md``).

`action.d/discord-notify.conf` is a NOTIFY-ONLY fail2ban action: on
ban/unban it POSTs a message to a Discord webhook whose URL comes from
the FAIL2BAN_DISCORD_WEBHOOK_URL env var (resolved by render-jail.sh,
same envsubst path as the cloudflare bouncer). It's opt-in (add
`discord-notify` to FAIL2BAN_ACTION) and no-ops when the URL is empty.

This test asserts the static wiring contract (the action file shape,
the env placeholders, render-jail.sh's allowlist, the compose
pass-through, and the .env.example documentation) — the same style as
test_fail2ban_cloudflare_bouncer.py. Live delivery (POST hits a real
Discord webhook) is operator-verified, not exercised here.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_ACTION_CONFIG = (
    _REPO_ROOT / "docs/integrations/fail2ban/action.d/discord-notify.conf"
)
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"


def _text(p: Path) -> str:
    return p.read_text()


def test_discord_action_file_exists():
    assert _ACTION_CONFIG.is_file(), (
        f"discord-notify action config missing at {_ACTION_CONFIG}"
    )


def test_discord_action_posts_on_ban_and_unban():
    """Defines both actionban + actionunban, each a curl POST to the
    webhook (notify-only — no ban/firewall call)."""
    text = _text(_ACTION_CONFIG)
    assert "actionban" in text
    assert "actionunban" in text
    assert "curl" in text
    # Posts JSON to the webhook; Discord webhooks take a `content` field.
    assert "Content-Type: application/json" in text
    assert "content" in text
    assert "<webhook_url>" in text


def test_discord_action_init_uses_env_placeholders():
    """The [Init] block envsubst-resolves the FAIL2BAN_DISCORD_* env
    vars so fail2ban reads real values."""
    text = _text(_ACTION_CONFIG)
    for placeholder in ("${FAIL2BAN_DISCORD_WEBHOOK_URL}",
                        "${FAIL2BAN_DISCORD_USERNAME}"):
        assert placeholder in text, (
            f"discord-notify.conf [Init] missing {placeholder}"
        )


def test_discord_action_noops_when_url_empty():
    """Both actions guard the curl on a non-empty webhook URL, so
    leaving `discord-notify` in FAIL2BAN_ACTION without a URL set is
    harmless (no curl fires)."""
    text = _text(_ACTION_CONFIG)
    # The POSIX `[ -n "<webhook_url>" ]` guard appears for both actions.
    assert text.count('[ -n "<webhook_url>" ]') >= 2, (
        "actionban + actionunban must each guard on a non-empty webhook URL"
    )


def test_render_script_allowlist_includes_discord_vars():
    """render-jail.sh's allowlist must include the new placeholders or
    they pass through to fail2ban literally and break the action."""
    text = _text(_RENDER_SCRIPT)
    for v in ("FAIL2BAN_DISCORD_WEBHOOK_URL", "FAIL2BAN_DISCORD_USERNAME"):
        assert v in text, f"render-jail.sh allowlist missing {v}"


def test_compose_passes_discord_env():
    """The compose fail2ban environment block plumbs the Discord vars
    through (empty webhook default, named username default)."""
    with _COMPOSE.open() as f:
        compose = yaml.safe_load(f)
    env = compose["services"]["fail2ban"].get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    assert "FAIL2BAN_DISCORD_WEBHOOK_URL" in env
    assert "FAIL2BAN_DISCORD_USERNAME" in env


def test_env_example_documents_discord_webhook():
    """`.env.example` carries the FAIL2BAN_DISCORD_WEBHOOK_URL key so a
    fresh `.env` copy has the (empty) opt-in slot + the how-to comment."""
    text = _text(_ENV_EXAMPLE)
    assert "FAIL2BAN_DISCORD_WEBHOOK_URL" in text
    assert "discord-notify" in text, (
        ".env.example should explain opting in via FAIL2BAN_ACTION"
    )
