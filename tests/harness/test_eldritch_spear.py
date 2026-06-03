"""v2.99.144 — Eldritch Spear (Warlock invocation) extends
Eldritch Blast range from 120 ft to 300 ft.

RAW (PHB p.110): "When you cast Eldritch Blast, its range is
300 feet."

Server-side `_pc_eldritch_spear_range_ft(sheet, attack)` returns
300 when the attacker has the invocation AND the attack is
Eldritch Blast; otherwise 0. The /attack endpoint overrides the
sheet-authored ``range_str`` to "300 ft" before the v2.49.76
``_check_cast_range`` gate fires + before the broadcast payload
is built — so the chat card + the range-enforcement gate both
see the extended range.

Demo fixture: Magnus's seed gains the invocation on his feats
list. v2.99.144 ships the gate; tests verify the broadcast
carries the extended range when Magnus shoots EB and is
unchanged for non-EB attacks / non-invocation casters.

Tests:
  - Magnus's Eldritch Blast broadcast carries `range: "300 ft"`
  - Magnus's Quarterstaff broadcast keeps its 5 ft range (the
    invocation's name + EB gates short-circuit on non-EB)
  - A non-Warlock PC with a synthetic "Eldritch Blast" attack
    but no invocation gets the sheet-authored 120 ft (no
    override fires)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ELDRITCH_BLAST_INDEX = 1  # Magnus's attacks: [Quarterstaff, Eldritch Blast]
QUARTERSTAFF_INDEX = 0


async def _attack(gm_client, gm_ws, char_id, attack_index):
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": char_id,
            "attack_index": attack_index,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    return msg["data"]


async def test_eldritch_spear_extends_eldritch_blast_range(
    gm_client, gm_ws, roster,
):
    """Magnus's Eldritch Blast broadcast should carry
    `range: "300 ft"` (was 120 ft in the sheet). The v2.99.144
    override fires before the broadcast payload is built.
    """
    magnus = roster["Magnus Hexbinder"]
    data = await _attack(gm_client, gm_ws, magnus["id"], ELDRITCH_BLAST_INDEX)
    assert data.get("range") == "300 ft", (
        f"Eldritch Spear should extend EB range to 300 ft; got "
        f"range={data.get('range')!r}"
    )


async def test_eldritch_spear_does_not_affect_non_eb_attacks(
    gm_client, gm_ws, roster,
):
    """Magnus's Quarterstaff broadcast should keep its sheet-
    authored 5 ft range (Eldritch Spear's name-gate rejects
    non-EB attacks).
    """
    magnus = roster["Magnus Hexbinder"]
    data = await _attack(gm_client, gm_ws, magnus["id"], QUARTERSTAFF_INDEX)
    assert data.get("range") == "5 ft", (
        f"Quarterstaff range should stay 5 ft (Eldritch Spear's "
        f"EB-name gate rejects non-EB attacks); got "
        f"range={data.get('range')!r}"
    )


async def test_eldritch_spear_requires_invocation(
    gm_client, gm_ws, roster,
):
    """A non-Warlock PC with a synthetic EB attack but no
    invocation on feats should keep the sheet-authored 120 ft
    range. Krieger gets a temporary EB-named attack patched in.
    """
    krieger = roster["Krieger Stonefist"]
    synthetic = {
        "name": "Eldritch Blast (synthetic)",
        "attack_bonus": "+7",
        "damage": "1d10",
        "damage_type": "force",
        "range": "120 ft",
    }
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": [synthetic]},
        )
        data = await _attack(gm_client, gm_ws, krieger["id"], 0)
        assert data.get("range") == "120 ft", (
            f"Without the Eldritch Spear invocation, EB range should "
            f"stay sheet-authored 120 ft; got range={data.get('range')!r}"
        )
    finally:
        # Restore Krieger's seed attacks.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": [
                {"name": "Greataxe", "attack_bonus": "+7", "damage": "1d12+4",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Two-handed, heavy."},
                {"name": "Javelin", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "30/120 ft",
                 "desc": "Thrown."},
            ]},
        )
