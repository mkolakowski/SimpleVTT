"""v2.159.21 — exhaustion-levels Phase 4: Berserker Frenzy rage-end
retrofit (closes the v2.99.226 filed TODO + Phase E.8 of
docs/plans/class-content-status.md).

RAW PHB p.49: "When your rage ends, you suffer one level of
exhaustion (which you can't remove until you finish a long rest)."

Implementation:
  - /use_frenzy stamps `sheet._frenzied_this_rage: True` on the PC.
  - /end_buff (with key="rage") detects the flag, bumps
    `sheet.exhaustion_level` by 1 (clamps at 6, level 6 routes
    through the death-save state machine), clears the flag, mirrors
    the new level to the combatant, broadcasts `exhaustion_update`
    with source="frenzy_rage_end".

Tests cover:
  - Frenzy → end rage → exhaustion 0 → 1 (regression-safe baseline).
  - End rage without Frenzy → exhaustion unchanged.
  - Subsequent rage WITHOUT Frenzy after a frenzied rage → flag is
    cleared (no spurious bump).
  - Frenzy at exhaustion 5 → end rage → level 6 → PC dies.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


@pytest_asyncio.fixture
async def krieger_in_battle(gm_client, krieger):
    """Reset exhaustion + long rest, seed Krieger in active battle."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": krieger["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    # Clear any stale _frenzied_this_rage flag.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"_frenzied_this_rage": False},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_pfen_{krieger['id']}",
             "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 15, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    yield krieger
    # Teardown: reset exhaustion to 0.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": krieger["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )


async def _read_exhaustion(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    return int(sheet.get("exhaustion_level") or 0)


async def _read_frenzied_flag(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    return bool(sheet.get("_frenzied_this_rage"))


async def test_frenzy_then_end_rage_bumps_exhaustion(
    gm_client, krieger_in_battle,
):
    """v2.159.21 happy path. Krieger /use_rage → /use_frenzy → /end_buff
    with key=rage → exhaustion goes 0 → 1, flag cleared."""
    krieger = krieger_in_battle

    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text

    fr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": krieger["id"], "override": True},
    )
    assert fr.status_code == 200, fr.text
    # Flag should be set.
    assert await _read_frenzied_flag(gm_client, krieger["id"]) is True

    # End the rage.
    er = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert er.status_code == 200, er.text

    # Exhaustion bumped + flag cleared.
    assert await _read_exhaustion(gm_client, krieger["id"]) == 1
    assert await _read_frenzied_flag(gm_client, krieger["id"]) is False


async def test_end_rage_without_frenzy_no_exhaustion(
    gm_client, krieger_in_battle,
):
    """Krieger rages without frenzy → /end_buff rage → exhaustion
    stays 0 (no spurious bump)."""
    krieger = krieger_in_battle

    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text

    er = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert er.status_code == 200, er.text

    assert await _read_exhaustion(gm_client, krieger["id"]) == 0


async def test_subsequent_rage_without_frenzy_no_exhaustion(
    gm_client, krieger_in_battle,
):
    """v2.159.21 flag-cleanup regression. First rage with Frenzy → +1
    exhaustion. Second rage WITHOUT Frenzy → +0 (flag cleared after
    first rage-end)."""
    krieger = krieger_in_battle

    # Rage + frenzy + end → exhaustion 1.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": krieger["id"], "override": True},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert await _read_exhaustion(gm_client, krieger["id"]) == 1

    # Second rage — NO frenzy this time. End it.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    # Should stay at 1 — no second bump.
    assert await _read_exhaustion(gm_client, krieger["id"]) == 1


async def test_frenzy_at_lv5_end_rage_kills(
    gm_client, krieger_in_battle,
):
    """v2.159.21 death routing. Krieger at exhaustion=5 → rage +
    frenzy → end rage → level 6 → death_saves.status = "dead"."""
    krieger = krieger_in_battle

    # Set exhaustion to 5.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": krieger["id"], "level": 5},
    )

    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_frenzy",
        json={"character_id": krieger["id"], "override": True},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )

    # Exhaustion = 6, death_saves.status = "dead".
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    assert int(sheet.get("exhaustion_level") or 0) == 6
    ds = sheet.get("death_saves") or {}
    assert ds.get("status") == "dead"
