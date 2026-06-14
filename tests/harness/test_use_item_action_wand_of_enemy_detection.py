"""v2.277.0 — charged-items Phase 1 (closes the plan): Wand of Enemy
Detection (RAW DMG p.211, rare, attunement). The last named plan item —
a utility ``action_kind: "buff"`` charge action, the same shape as Gem of
Seeing: the ``detect`` action routes through the shared
``_use_item_action_buff`` handler (no save, no damage), spending 1 of 7
charges and installing the ``enemy-detection`` buff template (60-ft
hostile-direction sense, 10 rounds = 1 minute) on the wielder's own
combatant. The ``summary_verb`` override makes the chat card read
"activates" instead of the gem's "gazes through".

Demo fixture: Pip Nimblefingers (Halfling Rogue) carries an equipped +
attuned Wand of Enemy Detection + a 7-charge resource row at key
``wand-of-enemy-detection``.

Tests:
  - happy path: detect with Pip in an active battle → ok, action_kind
    "buff", buff_key "enemy-detection", charges_spent=1,
    buff_installed=True, duration_rounds=10, resource 7 → 6, and the
    buff lands on Pip's combatant.
  - drained wand (0 charges) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "wand-of-enemy-detection"


def _mkc(cid, char_id=None, name="X", hp_max=200, ac=10):
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


async def _wand_inv_idx(gm_client, char_id):
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            return i
    raise AssertionError("Pip has no wand-of-enemy-detection inventory item")


def _pip(roster):
    for name, rec in roster.items():
        if "Pip" in name:
            return rec
    raise AssertionError(f"no Pip in roster: {list(roster)}")


@pytest_asyncio.fixture
async def pip(roster):
    return _pip(roster)


@pytest_asyncio.fixture
async def pip_full_wand(gm_client, pip):
    """Force-reseed Pip's Wand of Enemy Detection to a full 7 charges,
    restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 7, "max": 7}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield pip
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_wand_of_enemy_detection_installs_buff(gm_client, pip_full_wand):
    """Happy path: detect with Pip in an active battle → action_kind
    "buff", buff_key "enemy-detection", charges_spent=1,
    buff_installed=True, duration_rounds=10, resource 7 → 6."""
    pip = pip_full_wand
    idx = await _wand_inv_idx(gm_client, pip["id"])
    p_cid = f"tok_wed1_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(p_cid, pip["id"], name=pip["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "detect",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "buff"
    assert data["buff_key"] == "enemy-detection"
    assert data["charges_spent"] == 1
    assert data["buff_installed"] is True
    assert data["duration_rounds"] == 10
    assert data["resource"]["current"] == 6  # 7 → 6

    # The enemy-detection buff lands on Pip's combatant.
    battle_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combatants = (
        ((battle_resp.json() or {}).get("battle") or {}).get("combatants") or []
    )
    me = next((c for c in combatants if c.get("id") == p_cid), None)
    assert me is not None
    keys = {b.get("key") for b in (me.get("buffs") or []) if isinstance(b, dict)}
    assert "enemy-detection" in keys


async def test_wand_of_enemy_detection_empty_returns_409(gm_client, pip):
    """Drain the wand to 0 charges via /sheet-fields, then try to detect →
    409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _wand_inv_idx(gm_client, pip["id"])
        p_cid = f"tok_wed2_pip_{pip['id']}"
        await _seed_battle(gm_client, [
            _mkc(p_cid, pip["id"], name=pip["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "detect",
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"resources": snapshot},
        )
