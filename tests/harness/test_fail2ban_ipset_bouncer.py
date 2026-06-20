"""v2.473.0 — Phase 4e of
``docs/plans/fail2ban-crowdsec-integration.md``. Verifies the
ipset bouncer action + the privilege-elevating compose override.

Phase 4e ships:
- ``docs/integrations/fail2ban/action.d/ipset-bouncer.conf`` —
  the fail2ban action that adds banned IPs to an ipset and drops
  matching packets via an iptables rule.
- ``docs/integrations/fail2ban/docker-compose.fail2ban-ipset.yml``
  — a compose override layered on top of the main compose file
  that adds ``network_mode: host`` + ``cap_add: [NET_ADMIN]`` so
  the in-container ipset / iptables commands reach the host's
  network namespace.

The override is deliberately OPT-IN TWICE — the operator must
both enable ``--profile fail2ban`` AND pass ``-f
docs/integrations/.../docker-compose.fail2ban-ipset.yml`` to load
the privileged config. This test set anchors that contract.

Live-banning smoke test (privileged stack actually fires an
``ipset add`` against a synthetic IP) lives in Phase 4f — Phase
4e is just config-shape validation.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BASE_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_OVERRIDE = (
    _REPO_ROOT
    / "docs/integrations/fail2ban/docker-compose.fail2ban-ipset.yml"
)
_ACTION = (
    _REPO_ROOT
    / "docs/integrations/fail2ban/action.d/ipset-bouncer.conf"
)


def _load(p: Path) -> dict:
    with p.open() as f:
        return yaml.safe_load(f)


def _load_text(p: Path) -> str:
    return p.read_text()


def test_ipset_action_file_exists():
    assert _ACTION.is_file(), (
        f"ipset-bouncer action config missing at {_ACTION}"
    )


def test_ipset_action_has_create_and_destroy_lifecycle():
    """The action must define actionstart (create ipset + iptables
    rule) and actionstop (tear them down), plus actionban /
    actionunban for per-IP add/remove. fail2ban parses errors out
    if these aren't present."""
    text = _load_text(_ACTION)
    for key in ("actionstart", "actionstop", "actionban", "actionunban"):
        assert key in text, (
            f"ipset action config missing {key} definition"
        )
    # The lifecycle has to use ipset + iptables — otherwise it's
    # just a no-op action.
    assert "ipset" in text, "action body must call ipset"
    assert "iptables" in text, "action body must call iptables"


def test_ipset_actionstart_is_idempotent():
    """The actionstart uses -exist on ipset create (so a re-run
    after a crash doesn't EBUSY) and idempotent iptables -C ... ||
    iptables -I ... for the DROP rule. Anchors the safety property
    so a future edit can't introduce a hard-fail on restart."""
    text = _load_text(_ACTION)
    assert "ipset create -exist" in text, (
        "ipset create must use -exist for idempotence"
    )
    assert "iptables -C" in text, (
        "actionstart must check whether the iptables rule already "
        "exists before inserting"
    )


def test_ipset_actionban_uses_ip_and_bantime_placeholders():
    """The actionban must reference fail2ban's <ip> and <bantime>
    placeholders so per-IP bans land with the right expiry."""
    text = _load_text(_ACTION)
    # The actionban line specifically.
    actionban_lines = [
        line for line in text.splitlines()
        if line.strip().startswith("actionban")
    ]
    assert actionban_lines, "no actionban line found"
    joined = " ".join(actionban_lines)
    assert "<ip>" in joined, "actionban must reference <ip>"
    assert "<bantime>" in joined, "actionban must reference <bantime>"


def test_ipset_override_file_exists():
    """The privilege-elevating compose override ships next to the
    base configs."""
    assert _OVERRIDE.is_file(), (
        f"docker-compose.fail2ban-ipset.yml override missing at "
        f"{_OVERRIDE}"
    )


def test_override_sets_network_mode_host_and_net_admin():
    """The override is the only place ``network_mode: host`` +
    ``cap_add: NET_ADMIN`` land — the base compose stays
    unprivileged so the default ``--profile fail2ban`` flow can't
    accidentally elevate."""
    override = _load(_OVERRIDE)
    fail2ban = (override.get("services") or {}).get("fail2ban") or {}
    assert fail2ban.get("network_mode") == "host", (
        "override must set network_mode: host so ipset / iptables "
        "reach the host network namespace"
    )
    cap_add = fail2ban.get("cap_add") or []
    assert "NET_ADMIN" in cap_add, (
        f"override must add NET_ADMIN capability; got cap_add={cap_add}"
    )


def test_base_compose_does_not_elevate_fail2ban():
    """The base docker-compose.yml MUST leave the fail2ban service
    unprivileged. If a future edit added ``network_mode: host`` or
    ``cap_add: NET_ADMIN`` to the base service, every
    ``docker compose --profile fail2ban up`` run would silently
    elevate — defeating the opt-in design of Phase 4e."""
    base = _load(_BASE_COMPOSE)
    fail2ban = base["services"]["fail2ban"]
    assert fail2ban.get("network_mode") is None, (
        "base fail2ban service must NOT set network_mode; ipset "
        "privileges live in the docs/integrations override only"
    )
    assert not fail2ban.get("cap_add"), (
        "base fail2ban service must NOT carry cap_add; ipset "
        "privileges live in the docs/integrations override only"
    )


def test_override_only_touches_fail2ban_service():
    """The override is a minimal layer on top of the base compose —
    it must NOT redefine other services (db, app, backup, etc.) or
    pull in unrelated config. Anchors against scope creep that
    would turn this from a fail2ban override into a generic
    deployment-mode override."""
    override = _load(_OVERRIDE)
    services = override.get("services") or {}
    assert list(services.keys()) == ["fail2ban"], (
        f"override must only redefine fail2ban; got "
        f"services={list(services.keys())}"
    )
