"""v2.470.0 — Phase 4b of
``docs/plans/fail2ban-crowdsec-integration.md``. Verifies the
``fail2ban`` service block in ``docker-compose.yml``.

The compose block is profile-gated (``profiles: [fail2ban]``) so
``docker compose up`` doesn't start it by default. An operator
opts in with ``docker compose --profile fail2ban up``. This test
asserts the YAML contract that downstream phases depend on:
- The service name + image pin (Phase 4b chose
  ``crazymax/fail2ban:1.0.2``).
- The shared ``audit_logs`` volume is mounted read-only at the
  same path the app writes to in Phase 4a.
- The v2.424.0 reference filter + jail configs are mounted from
  ``docs/integrations/fail2ban/{filter.d,jail.d}``.
- The fail2ban ban DB has its own persistent named volume.

The live-container smoke test (bring up the profile + exec
``fail2ban-client status simplevtt-auth``) lands in Phase 4f.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"


def _load_compose() -> dict:
    with _COMPOSE.open() as f:
        return yaml.safe_load(f)


def test_fail2ban_service_exists():
    """``fail2ban`` is a top-level service in docker-compose.yml."""
    compose = _load_compose()
    services = compose.get("services") or {}
    assert "fail2ban" in services, (
        "fail2ban service missing from docker-compose.yml — Phase 4b "
        "of fail2ban-crowdsec-integration.md adds it"
    )


def test_fail2ban_service_is_profile_gated():
    """The service stays out of the default ``docker compose up`` —
    operator opts in with ``--profile fail2ban``."""
    compose = _load_compose()
    fail2ban = compose["services"]["fail2ban"]
    profiles = fail2ban.get("profiles") or []
    assert "fail2ban" in profiles, (
        "fail2ban service must be profile-gated; otherwise "
        "default `docker compose up` starts a container that "
        "needs the audit log volume the app populates"
    )


def test_fail2ban_image_pinned():
    """Image is pinned to ``crazymax/fail2ban:1.0.2`` (avoid
    ``latest`` to keep compose runs reproducible)."""
    compose = _load_compose()
    image = compose["services"]["fail2ban"].get("image")
    assert image and image.startswith("crazymax/fail2ban:"), (
        f"fail2ban image must be a pinned crazymax/fail2ban tag; "
        f"got {image!r}"
    )
    assert not image.endswith(":latest"), (
        "fail2ban image must be pinned, not :latest"
    )


def test_fail2ban_mounts_audit_logs_readonly():
    """The shared ``audit_logs`` volume from Phase 4a is mounted
    read-only at ``/var/log/simplevtt`` so the fail2ban filter can
    tail the canonical audit log."""
    compose = _load_compose()
    fail2ban = compose["services"]["fail2ban"]
    volumes = fail2ban.get("volumes") or []
    audit_mounts = [
        v for v in volumes
        if isinstance(v, str)
        and v.startswith("audit_logs:")
    ]
    assert audit_mounts, (
        "fail2ban must mount the audit_logs named volume; got "
        f"volumes={volumes}"
    )
    # The audit-logs mount must be read-only — fail2ban must not be
    # able to clobber the app's log (defense in depth against a
    # compromised fail2ban container).
    assert any(":ro" in v for v in audit_mounts), (
        f"audit_logs mount must be read-only; got {audit_mounts}"
    )


def test_fail2ban_mounts_reference_configs():
    """The v2.424.0 reference filter + jail configs at
    ``docs/integrations/fail2ban/{filter.d,jail.d}`` are mounted
    read-only into the fail2ban container."""
    compose = _load_compose()
    fail2ban = compose["services"]["fail2ban"]
    volumes = fail2ban.get("volumes") or []
    filter_mount = next(
        (v for v in volumes
         if isinstance(v, str)
         and "fail2ban/filter.d" in v),
        None,
    )
    jail_mount = next(
        (v for v in volumes
         if isinstance(v, str)
         and "fail2ban/jail.d" in v),
        None,
    )
    assert filter_mount is not None, (
        "fail2ban must mount docs/integrations/fail2ban/filter.d"
    )
    assert jail_mount is not None, (
        "fail2ban must mount docs/integrations/fail2ban/jail.d"
    )
    # Both should be read-only — operator-side config edits go
    # through the on-disk path, not via fail2ban-client.
    assert ":ro" in filter_mount, (
        f"filter.d mount must be read-only; got {filter_mount}"
    )
    assert ":ro" in jail_mount, (
        f"jail.d mount must be read-only; got {jail_mount}"
    )


def test_fail2ban_data_volume_declared():
    """The ban DB volume ``fail2ban_data`` is declared at the
    compose top-level (so bans survive container restarts)."""
    compose = _load_compose()
    volumes = compose.get("volumes") or {}
    assert "fail2ban_data" in volumes, (
        "fail2ban_data named volume must be declared at the compose "
        "top-level"
    )
    # And it must be referenced in the fail2ban service's volumes.
    fail2ban = compose["services"]["fail2ban"]
    fail2ban_volumes = fail2ban.get("volumes") or []
    assert any(
        isinstance(v, str) and v.startswith("fail2ban_data:")
        for v in fail2ban_volumes
    ), "fail2ban service must mount fail2ban_data"


def test_fail2ban_depends_on_app():
    """fail2ban depends on the app service so it doesn't start
    before the audit-log file exists."""
    compose = _load_compose()
    fail2ban = compose["services"]["fail2ban"]
    depends_on = fail2ban.get("depends_on") or []
    # depends_on can be a list of service names or a dict with
    # condition-keyed sub-objects; handle both shapes.
    if isinstance(depends_on, dict):
        assert "app" in depends_on, (
            f"fail2ban must depend on app; got {depends_on}"
        )
    else:
        assert "app" in depends_on, (
            f"fail2ban must depend on app; got {depends_on}"
        )
