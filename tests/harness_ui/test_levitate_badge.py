"""v2.285.0 — Boots of Levitation: levitate-at-will badge on the sheet.

The sheet (`app/templates/sheet_dnd5e.html`) renders a `#levitate-badge`
movement-trait chip when the server computes the `levitate_at_will` derived
flag (Boots of Levitation, RAW DMG p.155). The flag is server-rendered at
page load, so these tests PATCH Magnus Hexbinder's spare boots equipped +
attuned via httpx first, then drive the browser to assert the badge renders.
The seed keeps the boots inert (unequipped/unattuned), so a control PC shows
no badge. Inventory is restored on teardown.
"""
import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

_BOOTS_SLUG = "boots-of-levitation"


def _gm_client() -> httpx.Client:
    """A logged-in GM httpx client, ready to use directly (not as a context
    manager — `.post` has already opened it). Close it explicitly."""
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True)
    client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
    return client


def _sheet_json(client: httpx.Client, char_id: int) -> dict:
    resp = client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_levitate_badge_renders_when_boots_attuned(gm_page: Page, roster: dict):
    """With Magnus's Boots of Levitation equipped+attuned, the sheet renders
    the levitate-at-will badge naming the boots; restores inventory after."""
    magnus = roster["Magnus Hexbinder"]
    page = gm_page
    client = _gm_client()
    try:
        data = _sheet_json(client, magnus["id"])
        inv = list((data.get("sheet") or {}).get("inventory") or [])
        snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
        new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
        found = False
        for it in new_inv:
            if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG:
                it["equipped"], it["attuned"] = True, True
                found = True
        assert found, "Magnus has no boots-of-levitation item"
        client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": new_inv},
        )
        try:
            page.goto(sheet_url(magnus["id"]))
            badge = page.locator("#levitate-badge")
            expect(badge).to_be_visible(timeout=5000)
            assert "Boots of Levitation" in (badge.text_content() or ""), (
                f"expected the boots named in the badge; got "
                f"{badge.text_content()!r}"
            )
        finally:
            client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
                json={"inventory": snapshot},
            )
    finally:
        client.close()


def test_no_levitate_badge_for_baseline_pc(gm_page: Page, roster: dict):
    """A PC with no Boots of Levitation (Garrik) renders no levitate badge —
    proving the chip is item-sourced, not always-on."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))
    # Sheet body is up once the speed chip is visible.
    expect(page.locator("#speed-disp")).to_be_visible(timeout=5000)
    assert page.locator("#levitate-badge").count() == 0, (
        "unexpected levitate badge on a PC with no Boots of Levitation"
    )
