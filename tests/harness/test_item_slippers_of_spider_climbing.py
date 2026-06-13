"""v2.237.0 — Slippers of Spider Climbing (RAW DMG p.199, uncommon, no
attunement): while worn, you can move up, down, and across vertical surfaces
and upside down along ceilings, hands-free, with a climbing speed equal to
your walking speed.

The flag rides the `slippers-of-spider-climbing` catalog payload
(`spider_climb: True`), aggregates in `_equipped_item_effects` (boolean OR into
a new `spider_climb` field + `spider_climb_sources`), and surfaces on
`/sheet-json` as `derived.spider_climb = {sources}`. The climbing-speed numeric
is GM-narrated in v1 (same treatment as Potion of Climbing) — this exposes the
ability as a derived read.

Demo fixture: Pip Quickfingers (Halfling Rogue) wears them (no attunement — she
is already at the RAW 3/3 attunement cap with Cloak + Ring + Sword of
Sharpness) — on-theme for a rogue scaling walls.
"""
from .conftest import CAMPAIGN_ID

_SLIPPERS_SLUG = "slippers-of-spider-climbing"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_slippers_expose_spider_climb(gm_client, roster):
    """Happy path: Pip's `/sheet-json` reports `derived.spider_climb` with
    the slippers named in its sources."""
    pip = roster["Pip Quickfingers"]
    data = await _sheet_json(gm_client, pip["id"])
    sc = (data.get("derived") or {}).get("spider_climb")
    assert sc is not None, (
        f"expected derived.spider_climb, got: {data.get('derived')!r}"
    )
    assert any(
        "Slippers of Spider Climbing" in str(s) for s in sc.get("sources") or []
    ), f"expected the slippers named in sources, got: {sc!r}"


async def test_slippers_compose_with_goggles_darkvision(gm_client, roster):
    """The no-attunement spider-climb flag rides alongside Pip's Goggles of
    Night — both no-attunement wondrous items contribute their own derived
    surfaces from the same equipped-item walker."""
    pip = roster["Pip Quickfingers"]
    data = await _sheet_json(gm_client, pip["id"])
    derived = data.get("derived") or {}
    assert derived.get("spider_climb") is not None, derived
    inv = (data.get("sheet") or {}).get("inventory") or []
    assert any(
        isinstance(it, dict) and it.get("_slug") == "goggles-of-night"
        for it in inv
    ), "expected Pip to still carry the Goggles of Night"


async def test_slippers_unequip_drops_flag(gm_client, roster):
    """Unequipping the slippers removes `derived.spider_climb`. Restores the
    original inventory on teardown."""
    pip = roster["Pip Quickfingers"]
    data = await _sheet_json(gm_client, pip["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _SLIPPERS_SLUG),
        None,
    )
    assert idx is not None, "Pip has no Slippers of Spider Climbing item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, pip["id"])
        assert "spider_climb" not in (data2.get("derived") or {}), (
            f"expected no spider_climb after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
