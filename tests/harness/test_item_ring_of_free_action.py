"""v2.240.0 — Ring of Free Action (RAW DMG p.191, rare, attunement): while
worn, difficult terrain costs no extra movement, and magic can neither reduce
your speed nor cause you to be paralyzed or restrained.

The flag rides the `ring-of-free-action` catalog payload (`free_action: True`,
`requires_attunement: True`), aggregates in `_equipped_item_effects` (boolean
OR into a new `free_action` field + `free_action_sources`), and surfaces on
`/sheet-json` as `derived.free_action = {sources}`. The effect is descriptive
in v1 — this exposes the ability as a derived read.

Demo fixture: Brakka Wildmane (Path of the Beast Barbarian) wears it as her
3rd attuned item (after the Belt of Giant Strength + Ioun Stone of
Constitution) — on-theme for an unrestrained beast barbarian.
"""
from .conftest import CAMPAIGN_ID

_RING_SLUG = "ring-of-free-action"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_ring_of_free_action_exposes_flag(gm_client, roster):
    """Happy path: Brakka's `/sheet-json` reports `derived.free_action` with
    the ring named in its sources."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    fa = (data.get("derived") or {}).get("free_action")
    assert fa is not None, (
        f"expected derived.free_action, got: {data.get('derived')!r}"
    )
    assert any(
        "Ring of Free Action" in str(s) for s in fa.get("sources") or []
    ), f"expected the ring named in sources, got: {fa!r}"


async def test_ring_of_free_action_requires_attunement(gm_client, roster):
    """The ring is an attunement item — the flag only surfaces while
    `attuned: True`. Dropping attunement removes `derived.free_action`;
    restores the original inventory on teardown."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _RING_SLUG),
        None,
    )
    assert idx is not None, "Brakka has no Ring of Free Action item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, brakka["id"])
        assert "free_action" not in (data2.get("derived") or {}), (
            f"expected no free_action after un-attune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{brakka['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_ring_of_free_action_composes_with_str_override(gm_client, roster):
    """The free-action flag rides alongside Brakka's Belt of Giant Strength —
    her STR override still reports on `derived.effective_abilities` from the
    same sheet, proving the new boolean field doesn't disturb the ability
    aggregation."""
    brakka = roster["Brakka Wildmane"]
    data = await _sheet_json(gm_client, brakka["id"])
    derived = data.get("derived") or {}
    assert derived.get("free_action") is not None, derived
    eff = derived.get("effective_abilities") or {}
    assert (eff.get("STR") or {}).get("effective") == 29, (
        f"expected STR effective 29 from the Belt to still report alongside "
        f"free_action, got: {eff!r}"
    )
