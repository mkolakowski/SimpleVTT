"""Regression net for the in-app ``/admin`` routes retired during the
Admin Center consolidation (``docs/plans/admin-center-consolidation.md``
Phase 4).

Retired so far:
  * v2.579.0 — user write surface (create / disable / reset-password /
    delete / scrub-audit-log) → Admin Center ``/users``.
  * v2.580.0 — on-demand demo reset (``POST /admin/demo/reset``) → Admin
    Center ``/tools``.
  * v2.581.0 — demo magic-link mint (``POST /admin/demo/mint-magic-link``)
    → Admin Center ``/tools`` (the public ``/demo-login`` redemption stays).

This file asserts those routes are GONE (no live duplicate write-path),
replacing the old ``test_admin_audit.py`` / ``test_admin_user_audit_scrub.py``
/ ``test_admin_demo_reset.py`` suites (superseded by the Admin Center
coverage in ``test_admin_center.py``).

The Center-side coverage for the moved behavior:
  * user create/disable/reset/delete → ``test_admin_center.py`` (the
    ``/users`` happy-path + MFA-gated destructive round-trips).
  * audit-log scrub → ``test_admin_center.py`` (``/users/{id}/scrub-audit-log``
    gate + JSON contract).
"""
import httpx
import pytest

BASE_URL = "http://localhost:8013"


def _app_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


# Each retired route + a method that used to be accepted. A removed route
# yields 404 (path no longer registered) or 405 (path prefix exists for
# another method); crucially never a 2xx/3xx (which would mean it still
# performs the action) — auth (401/403) is also acceptable since it still
# means the action did not run.
_RETIRED = [
    ("POST", "/admin/users"),
    ("POST", "/admin/users/1/disable"),
    ("POST", "/admin/users/1/reset_password"),
    ("POST", "/admin/users/1/delete"),
    ("POST", "/admin/users/1/scrub-audit-log"),
    # v2.580.0 — demo on-demand reset moved to the Admin Center (/tools).
    ("POST", "/admin/demo/reset"),
    # v2.581.0 — demo magic-link mint moved to the Admin Center (/tools).
    ("POST", "/admin/demo/mint-magic-link"),
]


@_LIVE
@pytest.mark.parametrize("method,path", _RETIRED)
def test_retired_inapp_user_routes_are_gone(method, path):
    """The in-app user write routes no longer exist — the request never
    succeeds (no 2xx/3xx). They moved to the Admin Center (Phase 4)."""
    r = httpx.request(method, f"{BASE_URL}{path}", timeout=5.0, follow_redirects=False)
    assert r.status_code in (401, 403, 404, 405), (
        f"{method} {path} returned {r.status_code} — expected the route to be retired"
    )
    # Belt-and-suspenders: definitely not a success/redirect (would imply the
    # write path still runs).
    assert not (200 <= r.status_code < 400), f"{method} {path} still live ({r.status_code})"
