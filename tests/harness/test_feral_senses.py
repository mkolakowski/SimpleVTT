"""v2.99.220 — Feral Senses (Ranger Lv 18+).

Phase F.3 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.92: "At 18th level, you gain preternatural senses that
help you fight creatures you can't see. When you attack a
creature you can't see, your inability to see it doesn't
impose disadvantage on your attack rolls against it."

v1 ships:
  - `_pc_has_feral_senses(sheet)` — Ranger Lv 18+ gate.
  - /attack accepts `attacker_cant_see_target: True` body field
    as a new disadvantage source.
  - When the attacker has Feral Senses, the "cant_see"
    disadvantage is suppressed.

The "aware of invisible creatures within 30 ft" half is filed
(would require fog-of-war / hidden-token state).

Tests:
  - Suppressed: Rowan Lv 18 attacks with `attacker_cant_see_target=True`
    → no disadvantage applied.
  - Control: Rowan Lv 7 default → disadvantage applies.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_fs_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_feral_senses_suppresses_cant_see_disadvantage(
    gm_client, roster,
):
    """Rowan Lv 18 + attacker_cant_see_target=True → no
    disadvantage applied (Feral Senses suppresses).
    """
    rowan = roster["Rowan Quickbow"]
    pip = roster["Pip Quickfingers"]
    pre_level = 7
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 18},
        class_slug="ranger",
    )
    try:
        pip_tok = f"tok_fs_{pip['id']}"
        await _seed_battle(gm_client, [_tok(rowan), _tok(pip)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": rowan["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "attacker_cant_see_target": True,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        rsa = data.get("roll_state_applied") or ""
        assert "cant_see" not in rsa, (
            f"v2.99.220: Feral Senses should suppress cant_see "
            f"disadvantage; got roll_state_applied={rsa!r}"
        )
        assert "disadvantage" not in rsa, (
            f"v2.99.220: at Lv 18 the cant_see disadvantage should "
            f"not apply; got roll_state_applied={rsa!r}"
        )
    finally:
        await _patch_sheet(
            gm_client, rowan["id"], {"level": pre_level},
            class_slug="ranger",
        )


async def test_feral_senses_cant_see_applies_below_lv18(
    gm_client, roster,
):
    """Control: Rowan at Lv 7 + attacker_cant_see_target=True →
    disadvantage applied (no Feral Senses gate).
    """
    rowan = roster["Rowan Quickbow"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_fs_{pip['id']}"
    await _seed_battle(gm_client, [_tok(rowan), _tok(pip)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_tok,
            "attacker_cant_see_target": True,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    rsa = data.get("roll_state_applied") or ""
    assert "cant_see" in rsa or "disadvantage_cant_see" in rsa, (
        f"v2.99.220: at Lv 7 the cant_see disadvantage should "
        f"apply; got roll_state_applied={rsa!r}"
    )
