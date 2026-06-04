"""v2.99.175 — Polymorph WIS save against unwilling targets.

RAW (PHB p.266): "An unwilling creature must make a Wisdom
saving throw to resist the effect. If it succeeds, it isn't
affected by this spell."

Implementation: /cast_polymorph accepts an optional
`unwilling: bool` body field. When True + a PC target is
supplied via target_combatant_id, the endpoint rolls the
target's WIS save vs the caster's spell save DC:
  - Save mod = WIS ability mod + proficiency bonus (if proficient)
  - DC = 8 + caster's proficiency + caster's spellcasting mod
  - On PASS: response carries `save_passed: True`,
    `concentration: False`, `ready_to_transform: False` —
    the concentration anchor is NOT installed.
  - On FAIL: response carries `save_passed: False`,
    `concentration: True` — concentration anchor installs as
    normal.

The slot is consumed in both cases (RAW: the spell was cast —
it just didn't take effect).

Tests:
  - Unwilling PC target (Krieger) → save rolled, response
    carries save_total + save_dc + save_target_name
  - Willing flag (unwilling=False, default) → no save rolled,
    save_rolled is False
  - Save passed (rigged via patching Krieger's WIS to 20) →
    no concentration anchor installed
"""
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def thalindra_with_l4_slot(gm_client, roster):
    """PATCH Thalindra with a L4 slot + Polymorph."""
    thalindra = roster["Thalindra Moonwhisper"]
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": stock_slots},
            "spells": [
                {"name": "Polymorph", "level": 4, "_slug": "polymorph",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    return thalindra


async def test_unwilling_target_save_rolled(
    gm_client, thalindra_with_l4_slot, roster,
):
    """Thalindra polymorphs Krieger (unwilling). Response carries
    save_rolled=True + save_total + save_dc + save_target_name.
    """
    thalindra = thalindra_with_l4_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_pws_th_{thalindra['id']}"
    kr_tok = f"tok_pws_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_id": kr_tok,
            "unwilling": True,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["save_rolled"] is True
    assert isinstance(data["save_total"], int)
    assert isinstance(data["save_dc"], int)
    assert data["save_dc"] >= 8
    assert data["save_target_name"] == krieger["name"]


async def test_willing_target_no_save(
    gm_client, thalindra_with_l4_slot, roster,
):
    """Without unwilling=True, no save is rolled."""
    thalindra = thalindra_with_l4_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_pws_no_th_{thalindra['id']}"
    kr_tok = f"tok_pws_no_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_id": kr_tok,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["save_rolled"] is False
    assert data["concentration"] is True
    assert data["ready_to_transform"] is True


async def test_save_pass_skips_concentration_anchor(
    gm_client, thalindra_with_l4_slot, roster,
):
    """Rig a save pass by PATCHing Krieger's WIS to 30 (impossibly
    high) and his WIS save to proficient. Save total will exceed
    any DC. Verify the concentration anchor is NOT installed.
    """
    thalindra = thalindra_with_l4_slot
    krieger = roster["Krieger Stonefist"]
    # Read Krieger's current sheet via roster (proxy — we PATCH
    # what we need to rig the save).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={
            "abilities": {"WIS": 30},
            "saving_throws": {"WIS": True},
        },
    )
    try:
        th_tok = f"tok_pws_pass_th_{thalindra['id']}"
        kr_tok = f"tok_pws_pass_kri_{krieger['id']}"
        await _seed_battle(gm_client, [
            _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
            _mkc(kr_tok, krieger["id"], name=krieger["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
            json={
                "character_id": thalindra["id"],
                "class_slug": "wizard",
                "slot_level": 4,
                "target_combatant_id": kr_tok,
                "unwilling": True,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["save_rolled"] is True
        assert data["save_passed"] is True, (
            f"Save with WIS 30 + prof should pass; got "
            f"total={data.get('save_total')} vs dc={data.get('save_dc')}"
        )
        assert data["concentration"] is False
        assert data["ready_to_transform"] is False
        # Thalindra should NOT have the concentration anchor.
        th_keys = await _get_buff_keys(gm_client, thalindra["id"])
        assert "concentration-polymorph" not in th_keys, (
            f"Concentration anchor should be skipped on save PASS; "
            f"got buffs={th_keys}"
        )
    finally:
        # Restore Krieger's original WIS / saves (Barbarian: WIS 10,
        # not proficient in WIS).
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={
                "abilities": {"WIS": 10},
                "saving_throws": {"STR": True, "CON": True},
            },
        )
