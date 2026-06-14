"""v2.250.0 — Mariner's Armor (RAW DMG p.181, uncommon, no attunement):
while wearing this armor you have a swimming speed equal to your walking
speed (+ a rise-to-surface-at-0-HP clause, GM-narrated in v1).

The swimming speed reuses the v2.242.0 `swim_speed` boolean-OR passive
verbatim — the flag rides the `mariners-armor` catalog payload
(`swim_speed: True`), aggregates in `_equipped_item_effects`, and surfaces on
`/sheet-json` as `derived.swim_speed = {sources}`. Zero new engine code; no
attunement, so the flag rides freely on any equipped Mariner's suit.

Demo fixture: Garrik Ironside (Fighter) wears a heavy (chain-mail-base, AC 16)
Mariner's Armor in place of his mundane chain mail — same AC and weight, so
nothing else on his sheet changes; it just adds the swim_speed passive. No
attunement, so it costs none of his 3/3 slots (Flame Tongue + Wand of
Lightning Bolts + Belt of Giant Strength).
"""
from .conftest import CAMPAIGN_ID

_ARMOR_SLUG = "mariners-armor"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _armor_index(data):
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _ARMOR_SLUG),
        None,
    )


async def test_mariners_armor_exposes_swim_speed(gm_client, roster):
    """Happy path: Garrik's `/sheet-json` reports `derived.swim_speed` with
    the armor named in its sources."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    sw = (data.get("derived") or {}).get("swim_speed")
    assert sw is not None, (
        f"expected derived.swim_speed, got: {data.get('derived')!r}"
    )
    assert any(
        "Mariner's Armor" in str(s) for s in sw.get("sources") or []
    ), f"expected the armor named in sources, got: {sw!r}"


async def test_mariners_armor_no_attunement_required(gm_client, roster):
    """The armor needs no attunement — the flag surfaces even though it has no
    `attuned` flag and Garrik's 3 attunement slots are filled by other items.
    `derived.swim_speed` present is the proof the no-attunement gate holds."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    derived = data.get("derived") or {}
    sw = derived.get("swim_speed")
    assert sw is not None, (
        f"expected swim_speed without attunement, got: {derived!r}"
    )
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    idx = _armor_index(data)
    assert idx is not None, "Garrik has no Mariner's Armor item"
    assert not inv[idx].get("attuned"), (
        f"Mariner's Armor should not be attuned, got: {inv[idx]!r}"
    )


async def test_mariners_armor_unequip_drops_flag(gm_client, roster):
    """Unequipping the armor removes `derived.swim_speed`. Restores the
    original inventory on teardown."""
    garrik = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, garrik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _armor_index(data)
    assert idx is not None, "Garrik has no Mariner's Armor item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, garrik["id"])
        assert "swim_speed" not in (data2.get("derived") or {}), (
            f"expected no swim_speed after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
