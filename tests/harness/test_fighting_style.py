"""v2.99.83 — Fighting Style auto-apply (Archery + Dueling).

RAW (PHB p.72-91): Lv 1 Fighter / Ranger and Lv 2 Paladin pick a
Fighting Style. v2.99.83 wires two attack-time bonuses:

  - Archery: +2 to ranged weapon attack rolls.
  - Dueling: +2 to damage when wielding a 1H melee weapon.

Both fire from /attack: Archery appends "+2" to the d20+bonus
expression; Dueling appends "+2" to the damage expression.

Demo fixtures:
  - Rowan Quickbow (Ranger Lv 5 Hunter, "archery") — Longbow
    auto-applies +2 to the d20 roll. v2.99.83 also strips the
    pre-baked +2 from the sheet's "+9" → "+7" so the end roll is
    identical.

  - No demo PC has Dueling. The harness PATCHes Caelan from
    Protection → Dueling, runs a 1H melee attack, asserts the
    damage expression carries +2, then restores Protection.

Tests:
- happy: Rowan's Longbow attack roll uses 1d20+7+2 (archery bonus
  visible in the breakdown).
- gate: Rowan's Shortsword (5 ft melee) does NOT get archery
  (helper short-circuits — range too short / no slash).
- happy: Caelan with Dueling fires a 1H melee attack and the
  damage expression includes +2.
- gate: Caelan with Dueling does NOT get +2 on a thrown spear
  (treated as ranged due to slash range — the demo doesn't have
  a thrown weapon for Caelan, so this is covered by the
  _attack_is_one_handed_melee helper's range check).
"""
import re
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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


def _parse_breakdown_terms(bd):
    """Parse the breakdown format ``1d20[17]=17 7 2  =>  26`` into
    the list of integer addend terms ([17, 7, 2]) and the trailing
    total (26). Returns (addends, total) or (None, None) if the
    format doesn't match.
    """
    m = re.match(r".*?=(-?\d+)\s+(.*?)\s+=>\s+(-?\d+)$", bd or "")
    if not m:
        return None, None
    d20_val = int(m.group(1))
    mid = m.group(2).strip()
    total = int(m.group(3))
    extras = []
    for tok in mid.split():
        try:
            extras.append(int(tok))
        except ValueError:
            pass
    return [d20_val] + extras, total


async def test_archery_applies_plus_2_to_ranged_attack(gm_client, gm_ws, roster):
    """Rowan's Longbow (range "150/600 ft") → Archery fires. The
    breakdown's addend list should include 7 (base) AND 2 (Archery).
    """
    rowan = roster["Rowan Quickbow"]
    # Longbow is attack index 0.
    data = await _attack(gm_client, gm_ws, rowan["id"], 0)
    bd = data.get("attack_breakdown") or ""
    addends, total = _parse_breakdown_terms(bd)
    assert addends is not None, f"could not parse breakdown {bd!r}"
    # d20 roll + 7 (base) + 2 (Archery) = three addends.
    assert 7 in addends and 2 in addends, (
        f"Archery +2 and base +7 should both be in the addends; "
        f"got {addends} bd={bd!r}"
    )
    assert sum(addends) == total, (
        f"breakdown total mismatch — addends {addends} sum != {total} ({bd!r})"
    )


async def test_archery_skipped_on_melee_attack(gm_client, gm_ws, roster):
    """Rowan's Shortsword (range "5 ft", no slash) → Archery
    short-circuits. Breakdown should NOT contain the Archery +2;
    only Rowan's base +7.
    """
    rowan = roster["Rowan Quickbow"]
    # Shortsword is attack index 1.
    data = await _attack(gm_client, gm_ws, rowan["id"], 1)
    bd = data.get("attack_breakdown") or ""
    addends, total = _parse_breakdown_terms(bd)
    assert addends is not None, f"could not parse breakdown {bd!r}"
    # Should only have d20 roll + 7 (base). No Archery +2.
    assert 7 in addends, f"base +7 should be in addends; got {addends}"
    assert 2 not in addends, (
        f"Archery should NOT fire on a melee shortsword (no +2 addend); "
        f"got {addends} bd={bd!r}"
    )


async def test_dueling_applies_plus_2_to_1h_melee_damage(gm_client, gm_ws, roster):
    """PATCH Caelan from Protection → Dueling. His Longsword (1H,
    range "5 ft" no slash) damage expression should carry the +2.
    Restore Protection in finally.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"fighting_style": "dueling"},
        )
        # Caelan's first attack is Longsword (1H melee). Find its
        # index by inspecting the live damage from the broadcast.
        data = await _attack(gm_client, gm_ws, caelan["id"], 0)
        dmg_expr = data.get("damage_expr") or ""
        # The damage expression should end with the Dueling +2.
        # Caelan's Longsword is "1d8+3" pre-Dueling → "1d8+3+2"
        # after Dueling. Match the trailing +2.
        assert dmg_expr.endswith("+2"), (
            f"Dueling +2 should be appended to the damage expression; "
            f"got {dmg_expr!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
            json={"fighting_style": "protection"},
        )


async def test_dueling_skipped_when_style_is_not_set(gm_client, gm_ws, roster):
    """Control: Caelan defaults to Protection (no Dueling); his
    Longsword damage expression does NOT carry the +2 Dueling
    addendum. Don't PATCH anything.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    data = await _attack(gm_client, gm_ws, caelan["id"], 0)
    dmg_expr = data.get("damage_expr") or ""
    # Protection style — no Dueling bonus appended. The expression
    # should be the raw sheet value (e.g. "1d8+3"). The trailing
    # "+2" pattern shouldn't appear unless it's part of the base
    # (e.g. "1d12+2" for a homebrew weapon — none on Caelan).
    assert not dmg_expr.endswith("+2"), (
        f"Caelan defaults to Protection — no Dueling +2 expected; "
        f"got {dmg_expr!r}"
    )
