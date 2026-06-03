"""v2.99.124 — damage immunity engine end-to-end test.

v2.99.124 adds the `_immunity_zero` engine helper, the
`damage_immunities: ["all"]` wildcard, and wires it into the PC
damage path in `_apply_damage_to_combatant`. Pre-v2.99.124 the
`damage_immunities` field was stored on sheets but NEVER read by
the damage application code — full immunity was descriptive only.

This test verifies the end-to-end immunity flow:
  - PATCH Krieger's sheet with `damage_immunities: ["all"]`
  - Tavik attacks; damage_applied is 0 regardless of the hit roll
  - target_resistance_applied is False (immunity supersedes
    resistance — they don't stack)

The NPC mirror (`_resistance_halve_npc` doesn't have an immunity
sibling yet) is filed for follow-up.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 100, "hp_max": 100,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def krieger_immune_to_all(gm_client, roster):
    """PATCH Krieger's sheet to add `damage_immunities: ["all"]`.
    Restore stock (empty list) on teardown.
    """
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"damage_immunities": ["all"]},
    )
    yield krieger
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"damage_immunities": []},
    )


async def test_all_immunity_zeroes_damage(
    gm_client, krieger_immune_to_all, roster,
):
    """Krieger has `damage_immunities: ["all"]`. Tavik attacks with
    bludgeoning. Damage_applied should be 0 (immunity → 0 damage,
    RAW PHB p.197).
    """
    krieger = krieger_immune_to_all
    tavik = roster["Brother Tavik Stonebrow"]
    tv_tok = f"tok_imm_tv_{tavik['id']}"
    kr_tok = f"tok_imm_kr_{krieger['id']}"
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
            _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": kr_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            # Hit landed; damage_applied should be 0.
            assert data.get("damage_applied") == 0, (
                f"'all' immunity should zero damage_applied; "
                f"got {data.get('damage_applied')} "
                f"(target_resistance_applied="
                f"{data.get('target_resistance_applied')})"
            )
            # Immunity should suppress resistance — they don't stack.
            assert data.get("target_resistance_applied") is False, (
                f"Immunity supersedes resistance; "
                f"target_resistance_applied should be False, "
                f"got {data.get('target_resistance_applied')}"
            )
            return
    raise AssertionError("no hit in 15 tries")


async def test_specific_type_immunity_zeroes_matching_damage(
    gm_client, roster,
):
    """Krieger gets `damage_immunities: ["bludgeoning"]`. Tavik's
    bludgeoning Warhammer → damage_applied = 0. Confirms the
    per-type branch (not just the "all" wildcard).
    """
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"damage_immunities": ["bludgeoning"]},
    )
    try:
        tavik = roster["Brother Tavik Stonebrow"]
        tv_tok = f"tok_imm_b_tv_{tavik['id']}"
        kr_tok = f"tok_imm_b_kr_{krieger['id']}"
        for _ in range(15):
            await _seed_battle(gm_client, [
                _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
                _mkc(kr_tok, krieger["id"], name=krieger["name"],
                     speed_walk=40),
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": tavik["id"],
                    "attack_index": 0,
                    "target_combatant_id": kr_tok,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if data.get("hit"):
                # Bludgeoning hit on a bludgeoning-immune target.
                # NOTE: Tavik's Divine Strike adds radiant damage,
                # which is NOT bludgeoning-immune. So damage_applied
                # may not be exactly 0 — only the bludgeoning
                # component is immune. The Warhammer's bludgeoning
                # roll IS zeroed though. Without a separate
                # per-component breakdown, the test asserts that
                # damage is reduced significantly.
                # Pin: damage_applied <= max Divine Strike roll
                # (1d8 = 8 non-crit; 2d8 = 16 crit).
                max_radiant = 16 if data.get("is_crit") else 8
                assert data.get("damage_applied", 0) <= max_radiant, (
                    f"bludgeoning immunity should zero the Warhammer "
                    f"component; got {data.get('damage_applied')} "
                    f"(crit={data.get('is_crit')}, max radiant only "
                    f"= {max_radiant})"
                )
                return
        raise AssertionError("no hit in 15 tries")
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"damage_immunities": []},
        )


async def test_no_immunity_baseline_full_damage(gm_client, roster):
    """Control: Krieger has no damage_immunities (stock). Tavik's
    attack lands normally with full damage_applied > 0.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    tv_tok = f"tok_imm_ctl_tv_{tavik['id']}"
    kr_tok = f"tok_imm_ctl_kr_{krieger['id']}"
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
            _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": kr_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit") and (data.get("damage_applied") or 0) > 0:
            return  # full damage applied as expected
    raise AssertionError("no nonzero-damage hit in 15 tries")
