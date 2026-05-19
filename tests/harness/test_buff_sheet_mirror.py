"""Phase C.3 — character.sheet["_buffs_active"] mirror tests.

v2.19.2: every buff install / remove / auto-expire path mirrors the
combatant's buff list to the character sheet's ``_buffs_active`` field.
This gives the full-sheet "Active Effects" panel a persistent data
source independent of the hub battle state (which is in-memory only).

Tests:
  - /use_rage updates _buffs_active with the rage buff
  - /end_buff clears the _buffs_active entry
  - /cast_hunters_mark updates _buffs_active
  - PUT /battle with a tick'd buff list updates _buffs_active too
    (mirrors the GM auto-expire path)
  - duration_rounds / duration_max are stripped from the sheet mirror
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger_full(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


@pytest_asyncio.fixture
async def rowan_full(gm_client, roster):
    rowan = roster["Rowan Quickbow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    return rowan


async def _seed_battle_with(gm_client, char_ids: list[int]) -> None:
    combatants = []
    for cid in char_ids:
        combatants.append({
            "id": f"tok_test_{cid}",
            "char_id": cid,
            "name": f"PC {cid}",
            "initiative": 10,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_use_rage_mirrors_to_sheet(gm_client, krieger_full):
    """After /use_rage, char.sheet["_buffs_active"] contains the rage
    buff. duration_rounds and duration_max are stripped."""
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text

    # Read /buffs — both live (hub) + sheet mirror.
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Live hub buff has duration_rounds set.
    assert len(data["buffs"]) == 1
    assert data["buffs"][0]["key"] == "rage"
    assert data["buffs"][0]["duration_rounds"] == 10

    # Sheet mirror has duration_rounds and duration_max stripped.
    assert len(data["sheet_buffs"]) == 1
    sheet_rage = data["sheet_buffs"][0]
    assert sheet_rage["key"] == "rage"
    assert sheet_rage["name"] == "Rage"
    assert "duration_rounds" not in sheet_rage
    assert "duration_max" not in sheet_rage
    # Effects field is preserved (Phase B intercept will read this).
    assert sheet_rage["effects"]["melee_str_damage_bonus"] == 2


async def test_end_buff_clears_sheet_mirror(gm_client, krieger_full):
    """After /end_buff, the sheet mirror loses the entry."""
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    # Sanity check the sheet has rage.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert len(r.json()["sheet_buffs"]) == 1

    # End it.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert r.status_code == 200

    # Sheet mirror is empty.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert r.json()["sheet_buffs"] == []


async def test_hunters_mark_mirrors_to_sheet(gm_client, rowan_full, roster):
    """After /cast_hunters_mark, sheet mirror has the buff with target
    info preserved + duration stripped."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    await _seed_battle_with(gm_client, [rowan["id"], pip["id"]])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/buffs",
    )
    data = r.json()
    assert len(data["sheet_buffs"]) == 1
    hm = data["sheet_buffs"][0]
    assert hm["key"] == "hunters-mark"
    assert hm["concentration"] is True
    assert hm["target_character_id"] == pip["id"]
    # Effects preserved for the (B) Phase B intercept.
    assert hm["effects"]["weapon_hit_bonus_dice"] == "1d6"
    # Duration fields stripped.
    assert "duration_rounds" not in hm
    assert "duration_max" not in hm


async def test_put_battle_mirrors_to_sheet(gm_client, krieger_full):
    """PUT /battle with mutated buffs (simulating the GM's auto-expire
    tick) updates each PC's sheet mirror too."""
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    # PUT a battle state with Krieger's rage duration ticked to 9.
    new_state = {
        "combatants": [{
            "id": f"tok_test_{krieger['id']}",
            "char_id": krieger["id"],
            "name": "Krieger",
            "initiative": 10,
            "hp_current": 55,
            "hp_max": 55,
            "buffs": [{
                "key": "rage",
                "name": "Rage",
                "icon": "🦬",
                "duration_rounds": 9,
                "duration_max": 10,
                "concentration": False,
                "effects": {"melee_str_damage_bonus": 2},
                "desc": "Ticked",
            }],
            "economy": {"action": False, "bonus": True, "reaction": False, "movement": 0},
        }],
        "turn_index": 0,
        "round": 1,
        "active": True,
    }
    r = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json=new_state,
    )
    assert r.status_code == 200

    # Sheet mirror reflects the new buff list (duration stripped).
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    sheet_buffs = r.json()["sheet_buffs"]
    assert len(sheet_buffs) == 1
    assert sheet_buffs[0]["key"] == "rage"
    assert sheet_buffs[0]["desc"] == "Ticked"  # the PUT'd desc wins
    assert "duration_rounds" not in sheet_buffs[0]


async def test_put_battle_clears_sheet_on_buff_drop(gm_client, krieger_full):
    """PUT /battle with an empty buff list (simulating GM auto-expire
    dropping a buff at 0 rounds) clears the sheet mirror too."""
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    # Confirm rage is mirrored.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert len(r.json()["sheet_buffs"]) == 1

    # PUT a state with empty buffs (auto-expire dropped rage).
    new_state = {
        "combatants": [{
            "id": f"tok_test_{krieger['id']}",
            "char_id": krieger["id"],
            "name": "Krieger",
            "initiative": 10,
            "hp_current": 55,
            "hp_max": 55,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        }],
        "turn_index": 0,
        "round": 1,
        "active": True,
    }
    r = await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json=new_state,
    )
    assert r.status_code == 200

    # Sheet mirror is empty.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert r.json()["sheet_buffs"] == []
