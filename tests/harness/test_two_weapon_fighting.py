"""v2.99.87 — Fighting Style: Two-Weapon Fighting (Fighter / Paladin / Ranger Lv 1-2).

RAW (PHB p.72): "When you engage in two-weapon fighting, you can
add your ability modifier to the damage of the second attack."

Off-hand attacks by RAW (PHB p.195) don't add the ability mod to
damage by default; the Two-Weapon Fighting style restores it.

Server-side ``_pc_two_weapon_fighting_eligible(sheet, attack)``
gates on (a) sheet.fighting_style == "two_weapon" and (b)
attack.off_hand == True. The mod is derived from
attack_bonus − proficiency_bonus (with a DEX/STR sheet-side
fallback when those fields aren't present). Appended to
damage_expr_raw before the standard roller.

Demo fixture: Rowan Quickbow (Ranger Lv 5 Hunter). v2.99.87 marks
his Shortsword as ``off_hand: True`` + drops the damage from
"1d6+4" to "1d6" (no-mod baseline). Rowan's actual style is
"archery"; the tests PATCH him to "two_weapon" to exercise the
restoration, then restore Archery.

Tests:
- happy: Rowan PATCHed to "two_weapon" + Shortsword (off-hand,
  damage "1d6") → damage expression carries the +4 DEX mod.
- gate: Rowan with default Archery + Shortsword → damage stays
  at "1d6" (no TWF, no mod restoration).
- gate: Rowan PATCHed to "two_weapon" + Longbow (NOT off-hand) →
  damage expression unchanged (TWF only fires on off-hand
  attacks).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LONGBOW_INDEX = 0
SHORTSWORD_INDEX = 1


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


async def test_twf_appends_ability_mod_to_off_hand_damage(gm_client, gm_ws, roster):
    """PATCH Rowan to "two_weapon" style. His Shortsword (off_hand,
    damage "1d6") rolls "1d6+4" at /attack time. Restore "archery"
    in finally.
    """
    rowan = roster["Rowan Quickbow"]
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"fighting_style": "two_weapon"},
        )
        data = await _attack(gm_client, gm_ws, rowan["id"], SHORTSWORD_INDEX)
        dmg_expr = data.get("damage_expr") or ""
        # Rowan's DEX 18 mod = +4. Damage expression should be
        # "1d6+4" (the helper appends the mod to the no-mod baseline).
        assert dmg_expr.endswith("+4"), (
            f"TWF should append +4 to off-hand Shortsword damage; "
            f"got {dmg_expr!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"fighting_style": "archery"},
        )


async def test_twf_skipped_when_style_is_archery(gm_client, gm_ws, roster):
    """Default Rowan (Archery) + Shortsword (off_hand "1d6") →
    no TWF, no mod restoration. Damage expression stays "1d6".
    """
    rowan = roster["Rowan Quickbow"]
    data = await _attack(gm_client, gm_ws, rowan["id"], SHORTSWORD_INDEX)
    dmg_expr = data.get("damage_expr") or ""
    # No TWF style → no append. The damage stays at the sheet's
    # "1d6" baseline (off-hand without TWF gets no ability mod).
    assert dmg_expr == "1d6", (
        f"Default Archery should NOT add the off-hand mod; "
        f"got {dmg_expr!r}"
    )


async def test_twf_skipped_on_main_hand_attack(gm_client, gm_ws, roster):
    """PATCH Rowan to "two_weapon" + attack with his Longbow (NOT
    off_hand) → TWF helper short-circuits (attack.off_hand is
    falsy). The damage expression is whatever the sheet authored
    ("1d8+4"). Restore Archery in finally.
    """
    rowan = roster["Rowan Quickbow"]
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"fighting_style": "two_weapon"},
        )
        data = await _attack(gm_client, gm_ws, rowan["id"], LONGBOW_INDEX)
        dmg_expr = data.get("damage_expr") or ""
        # Longbow's authored damage is "1d8+4"; TWF skips (not off_hand)
        # so the only append is the v2.261.0 Bracers of Archery +2 ranged-
        # bow bonus → "1d8+4+2". The point of this test is that the TWF
        # off-hand ability mod is NOT added — the bracers +2 is a separate,
        # expected ranged-bow rider.
        assert dmg_expr == "1d8+4+2", (
            f"TWF should NOT fire on non-off-hand attacks (only the Bracers "
            f"of Archery +2 should append); got {dmg_expr!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"fighting_style": "archery"},
        )
