"""v2.99.93 — Eldritch Invocation: Hex Warrior.

RAW (PHB p.111): "When you attack with [a touched non-two-handed
weapon], you can use your Charisma modifier, instead of Strength
or Dexterity, for the attack and damage rolls."

Server-side ``_pc_hex_warrior_bonus(sheet, attack)`` returns the
delta ``CHA_mod - original_mod`` to append to both the d20 + bonus
expression AND the damage expression. Original mod derived from
``attack_bonus − proficiency_bonus`` (mirrors the v2.99.87 TWF
heuristic).

Demo fixture: Magnus's Quarterstaff is flagged ``hex_warrior: True``
and his feats list gains the invocation. Magnus's STR mod is +1
(STR 13), CHA mod is +3 (CHA 17), PB is +3 (Lv 5). Delta = +3 - +1
= +2; the d20 expression appends "+2" and the damage expression
appends "+2".

Tests:
- happy: Magnus's Quarterstaff attack breakdown includes the +2
  Hex Warrior delta; damage expression ends with "+2".
- gate: PATCH Magnus's feats to drop Hex Warrior → no swap;
  attack and damage stay at the sheet baselines.
- gate: Magnus's Eldritch Blast (no hex_warrior flag) is
  untouched by the Hex Warrior helper even with the invocation
  present (the +3 from Agonizing Blast is the only damage uplift
  on EB).
"""
import re
import pytest_asyncio

from .conftest import CAMPAIGN_ID


QUARTERSTAFF_INDEX = 0
ELDRITCH_BLAST_INDEX = 1


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


def _parse_breakdown_addends(bd):
    """Parse '1d20[17]=17 7 2 => 26' → [17, 7, 2]."""
    m = re.match(r".*?=(-?\d+)\s+(.*?)\s+=>\s+(-?\d+)$", bd or "")
    if not m:
        return None
    d20_val = int(m.group(1))
    extras = []
    for tok in m.group(2).strip().split():
        try:
            extras.append(int(tok))
        except ValueError:
            pass
    return [d20_val] + extras


@pytest_asyncio.fixture
async def magnus_with_hex_warrior(gm_client, roster):
    """PATCH Magnus's feats list to include Hex Warrior (+ keep
    Agonizing Blast / Repelling Blast / Lance of Lethargy for the
    other invocations to stay testable). Also PATCH his Quarterstaff
    with the hex_warrior: True flag. Restore the original feats +
    attacks at teardown.
    """
    magnus = roster["Magnus Hexbinder"]
    original_feats = [
        {"slug": "eldritch-invocation-agonizing-blast",
         "name": "Eldritch Invocation: Agonizing Blast"},
        {"slug": "eldritch-invocation-devils-sight",
         "name": "Eldritch Invocation: Devil's Sight"},
        {"slug": "eldritch-invocation-mask-of-many-faces",
         "name": "Eldritch Invocation: Mask of Many Faces"},
    ]
    hex_feats = original_feats + [
        {"slug": "eldritch-invocation-hex-warrior",
         "name": "Eldritch Invocation: Hex Warrior"},
    ]
    quarterstaff_baseline = {
        "name": "Quarterstaff", "attack_bonus": "+4", "damage": "1d6+1",
        "damage_type": "bludgeoning", "range": "5 ft",
    }
    quarterstaff_hex = dict(quarterstaff_baseline, hex_warrior=True)
    eldritch_blast = {
        "name": "Eldritch Blast (cantrip)", "attack_bonus": "+6",
        "damage": "1d10", "damage_type": "force", "range": "120 ft",
    }
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={
                "feats": hex_feats,
                "attacks": [quarterstaff_hex, eldritch_blast],
            },
        )
        yield magnus, original_feats, quarterstaff_baseline, eldritch_blast
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={
                "feats": original_feats,
                "attacks": [quarterstaff_baseline, eldritch_blast],
            },
        )


async def test_hex_warrior_swaps_str_for_cha_on_attack_and_damage(
    gm_client, gm_ws, magnus_with_hex_warrior,
):
    """Magnus's Quarterstaff (STR +1 + PB +3 baseline) with Hex
    Warrior should append +2 to BOTH the attack-roll expression
    (visible in attack_breakdown's addend list) AND the damage
    expression (visible in damage_expr ending with "+2").
    """
    magnus, _, _, _ = magnus_with_hex_warrior
    data = await _attack(gm_client, gm_ws, magnus["id"], QUARTERSTAFF_INDEX)
    bd = data.get("attack_breakdown") or ""
    addends = _parse_breakdown_addends(bd)
    assert addends is not None, f"couldn't parse breakdown {bd!r}"
    # d20 roll + 4 (base attack_bonus) + 2 (Hex Warrior delta).
    assert 4 in addends and 2 in addends, (
        f"Expected the sheet's +4 AND the Hex Warrior +2 in addends; "
        f"got {addends} bd={bd!r}"
    )
    dmg_expr = data.get("damage_expr") or ""
    assert dmg_expr.endswith("+2"), (
        f"Hex Warrior should append +2 to the damage expression; "
        f"got {dmg_expr!r}"
    )


async def test_hex_warrior_skipped_without_invocation(
    gm_client, gm_ws, magnus_with_hex_warrior, roster,
):
    """PATCH Magnus's feats to drop Hex Warrior (keep Quarterstaff's
    hex_warrior flag); attack + damage should fall back to the
    sheet baselines (no +2 delta).
    """
    magnus, original_feats, qstaff_baseline, eb = magnus_with_hex_warrior
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"feats": original_feats},
    )
    data = await _attack(gm_client, gm_ws, magnus["id"], QUARTERSTAFF_INDEX)
    bd = data.get("attack_breakdown") or ""
    addends = _parse_breakdown_addends(bd)
    assert addends is not None
    # Should only carry the d20 roll + 4 (base attack_bonus).
    assert 2 not in addends, (
        f"Without the invocation, Hex Warrior +2 should NOT fire; "
        f"got {addends} bd={bd!r}"
    )
    dmg_expr = data.get("damage_expr") or ""
    assert dmg_expr == "1d6+1", (
        f"Without the invocation, damage should stay at sheet baseline "
        f"'1d6+1'; got {dmg_expr!r}"
    )


async def test_hex_warrior_skipped_on_eldritch_blast(
    gm_client, gm_ws, magnus_with_hex_warrior,
):
    """Magnus's Eldritch Blast doesn't carry the hex_warrior flag,
    so the Hex Warrior helper short-circuits even with the
    invocation present. The damage expression carries the Agonizing
    Blast +3 (auto-applied) but NOT the Hex Warrior delta.
    """
    magnus, _, _, _ = magnus_with_hex_warrior
    data = await _attack(gm_client, gm_ws, magnus["id"], ELDRITCH_BLAST_INDEX)
    dmg_expr = data.get("damage_expr") or ""
    # Eldritch Blast: "1d10" + "+3" (Agonizing Blast) only.
    # No Hex Warrior delta — would require the hex_warrior flag.
    assert dmg_expr == "1d10+3", (
        f"Eldritch Blast should carry ONLY the Agonizing Blast +3, "
        f"not a Hex Warrior delta; got {dmg_expr!r}"
    )
