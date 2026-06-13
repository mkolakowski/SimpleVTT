"""v2.239.0 — Boots of Speed (RAW DMG p.155, rare, attunement): while worn,
a bonus action clicks the heels together to double your walking speed and give
any creature that makes an opportunity attack against you disadvantage, for up
to 10 minutes.

The flag rides the `boots-of-speed` catalog payload (`speed_doubling: True`,
`requires_attunement: True`), aggregates in `_equipped_item_effects` (boolean
OR into a new `speed_doubling` field + `speed_doubling_sources`), and surfaces
on `/sheet-json` as `derived.speed_doubling = {sources}`. The bonus-action
toggle + 10-minute budget are GM-narrated in v1 — this exposes the ability as
a derived read.

Demo fixture: Krieger Stonefist (Barbarian) wears them as his 3rd attuned item
(after the Ioun Stone of Wisdom + Ioun Stone of Awareness) — on-theme for a
barbarian closing distance on a target.
"""
from .conftest import CAMPAIGN_ID

_BOOTS_SLUG = "boots-of-speed"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_boots_of_speed_expose_speed_doubling(gm_client, roster):
    """Happy path: Krieger's `/sheet-json` reports `derived.speed_doubling`
    with the boots named in its sources."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    sd = (data.get("derived") or {}).get("speed_doubling")
    assert sd is not None, (
        f"expected derived.speed_doubling, got: {data.get('derived')!r}"
    )
    assert any(
        "Boots of Speed" in str(s) for s in sd.get("sources") or []
    ), f"expected the boots named in sources, got: {sd!r}"


async def test_boots_of_speed_require_attunement(gm_client, roster):
    """The boots are an attunement item — the flag only surfaces while
    `attuned: True`. Dropping attunement removes `derived.speed_doubling`;
    restores the original inventory on teardown."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG),
        None,
    )
    assert idx is not None, "Krieger has no Boots of Speed item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, krieger["id"])
        assert "speed_doubling" not in (data2.get("derived") or {}), (
            f"expected no speed_doubling after un-attune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_boots_of_speed_compose_with_awareness(gm_client, roster):
    """The speed-doubling flag rides alongside Krieger's Ioun Stone of
    Awareness — both equipped+attuned items contribute their own derived
    surfaces from the same equipped-item walker."""
    krieger = roster["Krieger Stonefist"]
    data = await _sheet_json(gm_client, krieger["id"])
    derived = data.get("derived") or {}
    assert derived.get("speed_doubling") is not None, derived
    assert derived.get("cannot_be_surprised") is not None, (
        f"expected cannot_be_surprised to still report alongside "
        f"speed_doubling, got: {derived!r}"
    )
