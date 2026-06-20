"""v2.469.0 — Phase 4a of
``docs/plans/fail2ban-crowdsec-integration.md``. RotatingFileHandler
tee for the ``simplevtt.audit`` logger.

The app container writes its canonical audit events to a file (in
addition to stdout) so the fail2ban container introduced in Phase
4b can tail it without docker-exec'ing into the app container. This
test verifies the wiring from the HTTP surface — there's no docker
SDK dependency here.

Tests:
  - ``/healthz`` surfaces ``audit_log_path`` and
    ``audit_log_enabled``.
  - The default path resolves to ``/var/log/simplevtt/audit.log``
    (per the docker-compose env-var default).
  - ``audit_log_enabled`` is True in the running container — proves
    the handler attached successfully on startup.
"""
from .conftest import CAMPAIGN_ID  # noqa: F401 — keeps the conftest fixture set loaded


async def test_healthz_surfaces_audit_log_config(gm_client):
    """``GET /healthz`` returns the audit-log path + enabled flag."""
    r = await gm_client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "audit_log_path" in body
    assert "audit_log_enabled" in body


async def test_healthz_audit_log_path_is_docker_compose_default(
    gm_client,
):
    """The docker-compose service sets ``AUDIT_LOG_PATH`` to the
    canonical location; verify the running container picked it up.
    Anchors that future changes to the env-var default don't
    silently drift away from the volume mount path."""
    r = await gm_client.get("/healthz")
    body = r.json()
    assert body["audit_log_path"] == "/var/log/simplevtt/audit.log"


async def test_healthz_audit_log_enabled_in_running_container(
    gm_client,
):
    """If the RotatingFileHandler couldn't attach (permission error,
    bad path), ``audit_log_enabled`` would be False and the startup
    log would carry a warning. In a healthy docker-compose run the
    flag must be True."""
    r = await gm_client.get("/healthz")
    body = r.json()
    assert body["audit_log_enabled"] is True, (
        "audit-log file handler did not attach on startup; check "
        "the simplevtt-app container logs for the warning"
    )
