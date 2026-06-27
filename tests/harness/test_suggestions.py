"""v2.716.0 — suggestion / issue reporting endpoints.

  - POST /api/suggestions            (any logged-in user) files a report.
  - GET  /api/admin/suggestions      (admin) lists reports.
  - PATCH /api/admin/suggestions/{id}(admin) updates status / admin_note.
  - DELETE /api/admin/suggestions/{id}(admin) deletes a report.

The demo GM is not a site admin locally (DEMO_GM_SITE_ADMIN=false), so the
admin-happy-path assertions run only when the client actually has admin
rights (CI / flipped env); the admin gate (403 for a non-admin) is always
asserted. The create + error paths run for any user.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _is_admin(client) -> bool:
    r = await client.get("/api/admin/suggestions")
    return r.status_code == 200


async def test_admin_home_renders_with_suggestions_section(gm_client):
    """The admin portal must not 500 with the new Suggestions section. A
    non-admin gets 403 before render; an admin (CI/flipped) renders 200 —
    either way, never a render-time 500."""
    # Seed at least one report so the section's table path is exercised.
    await gm_client.post(
        "/api/suggestions", json={"kind": "issue", "title": "Render-path seed"})
    r = await gm_client.get("/admin")
    assert r.status_code in (200, 403), r.text
    if r.status_code == 200:
        assert "Suggestions" in r.text


async def test_create_suggestion_happy(gm_client):
    r = await gm_client.post(
        "/api/suggestions",
        json={"kind": "issue", "title": "Token blur at zoom",
              "body": "Tokens look soft when zoomed in.",
              "page_url": f"/campaign/{CAMPAIGN_ID}"})
    assert r.status_code == 200, r.text
    s = r.json()["suggestion"]
    assert s["kind"] == "issue"
    assert s["title"] == "Token blur at zoom"
    assert s["status"] == "new"
    assert s["id"] > 0
    assert s["user_name"]


async def test_create_missing_title_400(gm_client):
    r = await gm_client.post(
        "/api/suggestions", json={"kind": "suggestion", "body": "no title"})
    assert r.status_code == 400, r.text


async def test_create_unknown_kind_defaults_to_suggestion(gm_client):
    r = await gm_client.post(
        "/api/suggestions",
        json={"kind": "rainbow", "title": "Defaulting kind test"})
    assert r.status_code == 200, r.text
    assert r.json()["suggestion"]["kind"] == "suggestion"


async def test_admin_list_requires_admin(alice_client):
    """A non-admin player can't list reports."""
    r = await alice_client.get("/api/admin/suggestions")
    assert r.status_code in (401, 403), r.text


async def test_admin_update_requires_admin(alice_client):
    r = await alice_client.patch(
        "/api/admin/suggestions/1", json={"status": "resolved"})
    assert r.status_code in (401, 403), r.text


async def test_my_suggestions_scoped_to_user(gm_client, alice_client):
    """GET /api/my-suggestions returns only the caller's own reports."""
    gm_title = "GM scope report ZZZ"
    al_title = "Alice scope report ZZZ"
    await gm_client.post("/api/suggestions", json={"title": gm_title})
    await alice_client.post("/api/suggestions", json={"title": al_title})
    gm_titles = [s["title"] for s in
                 (await gm_client.get("/api/my-suggestions")).json()["suggestions"]]
    al_titles = [s["title"] for s in
                 (await alice_client.get("/api/my-suggestions")).json()["suggestions"]]
    assert gm_title in gm_titles and gm_title not in al_titles
    assert al_title in al_titles and al_title not in gm_titles


async def test_my_suggestions_page_renders(gm_client):
    """The /my-suggestions page renders the caller's reports."""
    await gm_client.post(
        "/api/suggestions", json={"title": "Page render report QQQ"})
    r = await gm_client.get("/my-suggestions")
    assert r.status_code == 200, r.text
    assert "Page render report QQQ" in r.text
    assert "My suggestions" in r.text


async def test_count_requires_admin(alice_client):
    r = await alice_client.get("/api/admin/suggestions/count")
    assert r.status_code in (401, 403), r.text


async def test_count_returns_open_total_when_admin(gm_client):
    """The topnav badge's count endpoint returns the open (new/in_progress)
    total. Skipped when the client isn't a site admin."""
    if not await _is_admin(gm_client):
        pytest.skip("client is not a site admin (DEMO_GM_SITE_ADMIN=false)")
    # File a fresh 'new' report → the open count must be >= 1.
    await gm_client.post(
        "/api/suggestions", json={"kind": "issue", "title": "Count seed"})
    r = await gm_client.get("/api/admin/suggestions/count")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["open"], int) and body["open"] >= 1


async def test_admin_triage_flow(gm_client):
    """Admin-only happy path: list → the report appears; PATCH its status +
    note; DELETE it. Skipped when the client isn't a site admin."""
    if not await _is_admin(gm_client):
        pytest.skip("client is not a site admin (DEMO_GM_SITE_ADMIN=false)")
    # File a report to triage.
    created = (await gm_client.post(
        "/api/suggestions",
        json={"kind": "suggestion", "title": "Triage flow test",
              "body": "please triage"})).json()["suggestion"]
    sid = created["id"]
    # It shows up in the admin list.
    lst = (await gm_client.get("/api/admin/suggestions")).json()["suggestions"]
    assert any(s["id"] == sid for s in lst)
    # Update status + note.
    upd = await gm_client.patch(
        f"/api/admin/suggestions/{sid}",
        json={"status": "resolved", "admin_note": "fixed in v2.714.0"})
    assert upd.status_code == 200, upd.text
    assert upd.json()["suggestion"]["status"] == "resolved"
    assert upd.json()["suggestion"]["admin_note"] == "fixed in v2.714.0"
    # Bad status rejected.
    bad = await gm_client.patch(
        f"/api/admin/suggestions/{sid}", json={"status": "banana"})
    assert bad.status_code == 400, bad.text
    # Delete it.
    dele = await gm_client.delete(f"/api/admin/suggestions/{sid}")
    assert dele.status_code == 200, dele.text
    # 404 on a now-missing id.
    again = await gm_client.patch(
        f"/api/admin/suggestions/{sid}", json={"status": "new"})
    assert again.status_code == 404, again.text
