"""v2.259.0 — Gloves of Swimming and Climbing (RAW DMG p.171, uncommon,
attunement): while worn, climbing and swimming don't cost extra movement and
the wearer gains a +5 bonus to Strength (Athletics) checks made to climb or
swim.

The flag rides the `gloves-of-swimming-and-climbing` catalog payload
(`climb_swim_ease: True` + `requires_attunement: True`), aggregates in
`_equipped_item_effects` (boolean OR into a new `climb_swim_ease` field +
`climb_swim_ease_sources`), and surfaces on `/sheet-json` as
`derived.climb_swim_ease = {sources}`. Attunement-gated: the per-payload
attunement check drops the flag when worn-but-not-attuned (the Ring of X-ray
Vision pattern). The +5 Athletics climb/swim bonus is GM-narrated in v1.

Demo fixture: Mira Greenleaf (Druid) wears them attuned — completes her
aquatic kit alongside her Ring of Swimming + Cap of Water Breathing.
"""
from .conftest import CAMPAIGN_ID

_GLOVES_SLUG = "gloves-of-swimming-and-climbing"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_gloves_of_swimming_and_climbing_exposes_flag(gm_client, roster):
    """Happy path: Mira's `/sheet-json` reports `derived.climb_swim_ease` with
    the gloves named in its sources."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    cse = (data.get("derived") or {}).get("climb_swim_ease")
    assert cse is not None, (
        f"expected derived.climb_swim_ease, got: {data.get('derived')!r}"
    )
    assert any(
        "Gloves of Swimming and Climbing" in str(s)
        for s in cse.get("sources") or []
    ), f"expected the gloves named in sources, got: {cse!r}"


async def test_gloves_of_swimming_and_climbing_rides_alongside(gm_client, roster):
    """The attunement-gated flag rides alongside Mira's no-attunement aquatic
    items — `derived.water_breath` (Cap) and `derived.swim_speed` (Ring of
    Swimming) still report alongside `climb_swim_ease` from the same walker."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    derived = data.get("derived") or {}
    assert derived.get("climb_swim_ease") is not None, derived
    assert derived.get("water_breath") is not None, (
        f"expected water_breath alongside climb_swim_ease, got: {derived!r}"
    )
    assert derived.get("swim_speed") is not None, (
        f"expected swim_speed alongside climb_swim_ease, got: {derived!r}"
    )


async def test_gloves_of_swimming_and_climbing_detune_drops_flag(gm_client, roster):
    """Attunement gate: un-attuning the gloves (still equipped) removes
    `derived.climb_swim_ease`. Restores the original inventory on teardown."""
    mira = roster["Mira Greenleaf"]
    data = await _sheet_json(gm_client, mira["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _GLOVES_SLUG),
        None,
    )
    assert idx is not None, "Mira has no Gloves of Swimming and Climbing item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, mira["id"])
        assert "climb_swim_ease" not in (data2.get("derived") or {}), (
            f"expected no climb_swim_ease after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
