"""v2.232.0 — Ioun Stone of Mastery (RAW DMG p.176, legendary, attunement):
the last common SRD Ioun variant on the shared `ioun-stone` slug, and the
first to surface a proficiency-bonus override.

RAW: a dull grey ioun stone that orbits your head; while it does, your
proficiency bonus increases by 1. The +1 rides the inventory item via
`_proficiency_bonus: 1` (no ability payload), sums in
`_equipped_item_effects` (`proficiency_bonus`), surfaces on `/sheet-json` as
`derived.proficiency_bonus = {base, effective, bonus, sources}`, and is
appended to PROFICIENT saving throws in `/roll`.

Demo fixture: Quan Reelstep (Way of the Drunken Master Monk Lv 5) wears an
equipped + attuned Ioun Stone of Mastery — his 2nd attuned item (after the
Belt of Dwarvenkind, RAW max 3). He is class-proficient in STR + DEX saves
(PB 3 → 4), and the belt boosts only CON, so the Mastery +1 reads on his
DEX/STR saves unconfounded. CON saves (not proficient) guard the gate.
"""
from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_mastery_exposes_proficiency_bonus_on_sheet_json(gm_client, roster):
    """Happy path: Quan's `/sheet-json` reports `derived.proficiency_bonus`
    with base 3, effective 4, bonus 1, and the stone named in its sources."""
    quan = roster["Quan Reelstep"]
    data = await _sheet_json(gm_client, quan["id"])
    pb = (data.get("derived") or {}).get("proficiency_bonus")
    assert pb is not None, (
        f"expected derived.proficiency_bonus, got: {data.get('derived')!r}"
    )
    assert pb.get("base") == 3, pb
    assert pb.get("effective") == 4, pb
    assert pb.get("bonus") == 1, pb
    assert any(
        "Ioun Stone of Mastery" in str(s)
        for s in pb.get("sources") or []
    ), f"expected the stone named in sources, got: {pb!r}"


async def test_mastery_adds_to_proficient_save_roll(gm_client, roster):
    """A proficient DEX save roll on Quan picks up the Mastery +1 and the
    source attribution. The client bakes the base PB into the expression;
    the server appends the item +1 for the proficient save."""
    quan = roster["Quan Reelstep"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+6",
            "stat_key": "dex_save",
            "character_id": quan["id"],
            "note": "DEX save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Ioun Stone of Mastery" in breakdown, (
        f"expected 'Ioun Stone of Mastery' in save breakdown, got: {breakdown!r}"
    )
    assert "+1" in breakdown, (
        f"expected '+1' bonus annotation, got: {breakdown!r}"
    )


async def test_mastery_skips_non_proficient_save(gm_client, roster):
    """Guard: Quan is NOT proficient in CON saves, so a `con_save` roll
    must NOT pick up the Mastery +1 — the proficiency-bonus override only
    applies where the proficiency bonus is actually added (proficient
    saves), mirroring RAW."""
    quan = roster["Quan Reelstep"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "stat_key": "con_save",
            "character_id": quan["id"],
            "note": "CON save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Ioun Stone of Mastery" not in breakdown, (
        f"expected no Mastery bonus on non-proficient save, got: {breakdown!r}"
    )
