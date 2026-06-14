"""v2.286.0 — movement-trait badge strip on the character sheet.

The sheet (`app/templates/sheet_dnd5e.html`) renders a `#movement-traits`
strip of chips when the server computes item-sourced movement derived flags
(`_movement_traits_for_sheet`): flying speed, levitate at will, spider climb,
speed doubling. Each chip has id `#movement-trait-<flag>`.

Most demo carriers wear their item equipped+attuned at seed time, so those
chips render on a plain page load (no PATCH): Kael (Winged Boots → flying),
Pip (Slippers of Spider Climbing → spider climb), Krieger (Boots of Speed →
speed doubling). The Boots of Levitation are inert spare loot on Magnus, so
that one is exercised by PATCHing the boots on via httpx, then restoring.
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


def test_flying_speed_badge_for_kael(gm_page: Page, roster: dict):
    """Kael wears equipped+attuned Winged Boots at seed → the flying-speed
    chip renders naming the boots."""
    kael = roster["Kael Brightleaf"]
    page = gm_page
    page.goto(sheet_url(kael["id"]))
    badge = page.locator("#movement-trait-flying_speed")
    expect(badge).to_be_visible(timeout=5000)
    assert "Winged Boots" in (badge.text_content() or ""), (
        f"expected the boots named in the flying-speed chip; got "
        f"{badge.text_content()!r}"
    )


def test_spider_climb_badge_for_pip(gm_page: Page, roster: dict):
    """Pip wears equipped Slippers of Spider Climbing (no attunement) at seed
    → the spider-climb chip renders naming the slippers."""
    pip = roster["Pip Quickfingers"]
    page = gm_page
    page.goto(sheet_url(pip["id"]))
    badge = page.locator("#movement-trait-spider_climb")
    expect(badge).to_be_visible(timeout=5000)
    assert "Slippers of Spider Climbing" in (badge.text_content() or ""), (
        f"expected the slippers named in the spider-climb chip; got "
        f"{badge.text_content()!r}"
    )


def test_speed_doubling_badge_for_krieger(gm_page: Page, roster: dict):
    """Krieger wears equipped+attuned Boots of Speed at seed → the
    speed-doubling chip renders naming the boots."""
    krieger = roster["Krieger Stonefist"]
    page = gm_page
    page.goto(sheet_url(krieger["id"]))
    badge = page.locator("#movement-trait-speed_doubling")
    expect(badge).to_be_visible(timeout=5000)
    assert "Boots of Speed" in (badge.text_content() or ""), (
        f"expected the boots named in the speed-doubling chip; got "
        f"{badge.text_content()!r}"
    )


def test_levitate_badge_renders_when_boots_attuned(gm_page: Page, roster: dict):
    """Magnus's Boots of Levitation are inert spare loot — PATCH them
    equipped+attuned, assert the levitate chip renders naming the boots,
    then restore inventory."""
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
            badge = page.locator("#movement-trait-levitate_at_will")
            expect(badge).to_be_visible(timeout=5000)
            assert "Boots of Levitation" in (badge.text_content() or ""), (
                f"expected the boots named in the levitate chip; got "
                f"{badge.text_content()!r}"
            )
        finally:
            client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
                json={"inventory": snapshot},
            )
    finally:
        client.close()


def test_no_movement_traits_for_plain_pc(gm_page: Page, roster: dict):
    """Garrik carries no movement item → no `#movement-traits` strip renders,
    proving the chips are item-sourced, not always-on."""
    garrik = roster["Garrik Ironside"]
    page = gm_page
    page.goto(sheet_url(garrik["id"]))
    expect(page.locator("#speed-disp")).to_be_visible(timeout=5000)
    assert page.locator(".movement-trait-badge").count() == 0, (
        "unexpected movement-trait chip on a PC with no movement item"
    )
