"""v2.159.3 — magic-items-automation Phase 8c: Javelin of Lightning
(RAW DMG p.178). First line-AoE item that fires via the v2.158.82
/use_item_action endpoint. New handler takes a target_combatant_ids
list (the line creatures, GM-picked) and rolls a DC 13 DEX save for
each one → 4d6 lightning (half on pass). The javelin then becomes
nonmagical until the next dawn (state field _used_today: True);
v2.159.3's long-rest path clears the flag.

Demo fixture: Krieger Stonefist (Berserker Barbarian Lv 7) gets a
Javelin of Lightning at inventory_index 5. No attack entry needed —
the lightning chain fires via /use_item_action, and the player's
follow-up javelin melee strike on the target uses Krieger's normal
Javelin attack at attack_index 1.

Tests:
  - happy path: hurl with 2 targets → both get a save resolved +
    damage broadcast, item flips to _used_today=True.
  - already-used: trying to hurl again → 409 spent_until_dawn.
  - long-rest reset: rest=long clears _used_today, lets the player
    hurl again.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


KRIEGER_JAVELIN_INV_IDX = 5


def _mkc(cid, char_id=None, name="X", ac=1, hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


@pytest_asyncio.fixture
async def krieger_reset(gm_client, krieger):
    """Long-rest Krieger before each test so the javelin starts
    un-spent regardless of prior tests."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    yield krieger


async def test_javelin_lightning_hurl_two_targets(
    gm_client, krieger_reset,
):
    """v2.159.3 happy path. Hurl the Javelin with two line targets
    (synthetic Bandits with a real Hill Giant template would work
    too; we use cheap synthetic combatants here). Verify:
      - 200 response with results carrying both target ids
      - spent_until_dawn=True
      - Inventory item flipped to _used_today=True on the sheet
    """
    krieger = krieger_reset
    krieger_cid = f"tok_jol1_krieger_{krieger['id']}"
    a_cid = "tok_jol1_a"
    b_cid = "tok_jol1_b"
    await _seed_battle(gm_client, [
        _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
        _mkc(b_cid, None, name="Bandit Beta"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": KRIEGER_JAVELIN_INV_IDX,
            "action_key": "hurl-lightning",
            "target_combatant_ids": [a_cid, b_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["spent_until_dawn"] is True
    assert data["save_dc"] == 13
    assert data["save_ability"] == "DEX"
    # Both targets resolved (even if the save passed or failed —
    # we just need them in the results list).
    results = data.get("results") or []
    assert len(results) == 2
    target_ids = {r.get("combatant_id") for r in results}
    assert {a_cid, b_cid}.issubset(target_ids)

    # Sheet flag flipped.
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    assert sheet_resp.status_code == 200
    inventory = (sheet_resp.json().get("sheet") or {}).get("inventory") or []
    jav = inventory[KRIEGER_JAVELIN_INV_IDX]
    assert jav.get("_slug") == "javelin-of-lightning"
    assert jav.get("_used_today") is True, (
        f"Javelin should be _used_today=True after firing; "
        f"got {jav.get('_used_today')!r}"
    )


async def test_javelin_lightning_double_use_409(
    gm_client, krieger_reset,
):
    """v2.159.3: trying to hurl a javelin that's already spent
    today → 409 with error='spent_until_dawn'."""
    krieger = krieger_reset
    krieger_cid = f"tok_jol2_krieger_{krieger['id']}"
    a_cid = "tok_jol2_a"
    await _seed_battle(gm_client, [
        _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])

    # First hurl: 200.
    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": KRIEGER_JAVELIN_INV_IDX,
            "action_key": "hurl-lightning",
            "target_combatant_ids": [a_cid],
        },
    )
    assert first.status_code == 200, first.text

    # Second hurl: 409.
    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": KRIEGER_JAVELIN_INV_IDX,
            "action_key": "hurl-lightning",
            "target_combatant_ids": [a_cid],
        },
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body.get("error") == "spent_until_dawn"


async def test_javelin_lightning_long_rest_resets(
    gm_client, krieger_reset,
):
    """v2.159.3: long-rest reseed clears _used_today, lets the
    player hurl again."""
    krieger = krieger_reset
    krieger_cid = f"tok_jol3_krieger_{krieger['id']}"
    a_cid = "tok_jol3_a"
    await _seed_battle(gm_client, [
        _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])

    # First hurl → spent.
    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": KRIEGER_JAVELIN_INV_IDX,
            "action_key": "hurl-lightning",
            "target_combatant_ids": [a_cid],
        },
    )
    assert first.status_code == 200

    # Long rest.
    rest = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    assert rest.status_code == 200, rest.text

    # Hurl again → 200.
    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/use_item_action",
        json={
            "inventory_index": KRIEGER_JAVELIN_INV_IDX,
            "action_key": "hurl-lightning",
            "target_combatant_ids": [a_cid],
        },
    )
    assert second.status_code == 200, second.text
