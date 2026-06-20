"""v2.474.0 — Non-root hardening for the SimpleVTT app container.

The Dockerfile previously had no ``USER`` directive, so the
container ran every uvicorn worker as root. v2.474.0 ships a
``docker-entrypoint.sh`` that starts as root, chowns the named-
volume mount points (uploads_data, homebrew_data, audit_logs),
then drops privileges via ``gosu appuser`` before exec'ing
uvicorn.

This test asserts the running app process is **not** root. The
``/healthz`` response surfaces ``process_uid`` + ``process_user``;
on a healthy v2.474.0 container they read ``999`` /
``"appuser"``. A regression where someone removed the
ENTRYPOINT, the gosu drop, or the system-user creation surfaces
here as ``process_uid == 0``.

Note: ``docker compose exec -T app id`` will still report root.
That's expected — exec opens a NEW process inside the container
which doesn't go through the entrypoint. The test only cares
about the LIVE uvicorn process, which /healthz reports on.
"""


async def test_app_process_is_not_root(gm_client):
    """The running uvicorn process must NOT be root. Anchors the
    Dockerfile's ENTRYPOINT + gosu drop against regressions."""
    r = await gm_client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "process_uid" in body, (
        "/healthz must surface process_uid for the non-root check"
    )
    assert body["process_uid"] != 0, (
        f"app process is running as root (uid=0); "
        f"the v2.474.0 entrypoint drop didn't fire. "
        f"healthz response: {body}"
    )


async def test_app_process_user_is_appuser(gm_client):
    """The running uvicorn process runs as the ``appuser`` system
    account created in v2.474.0's Dockerfile."""
    r = await gm_client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("process_user") == "appuser", (
        f"app process must run as 'appuser' (got "
        f"{body.get('process_user')!r}); check that the Dockerfile "
        "still creates the user and the entrypoint still drops via "
        "gosu appuser"
    )


async def test_app_still_serves_audit_log_to_writable_path(gm_client):
    """Sanity check that the non-root drop didn't break the
    RotatingFileHandler write path — audit_log_enabled stays True
    because the v2.474.0 Dockerfile chowns /var/log/simplevtt to
    appuser before the entrypoint switches users."""
    r = await gm_client.get("/healthz")
    body = r.json()
    assert body.get("audit_log_enabled") is True, (
        "audit log handler failed to attach as appuser; check that "
        "the Dockerfile's chown -R covers /var/log/simplevtt"
    )
