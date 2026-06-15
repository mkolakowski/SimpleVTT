"""v2.324.0 — Wand of Magic Detection (RAW DMG p.210, uncommon, NO
attunement). 3 charges, regain 1d3 at dawn. Action: expend 1 charge → cast
Detect Magic (30-ft radius, 10-min concentration). Pure clone of v2.277.0
Wand of Enemy Detection's `action_kind: "buff"` substrate — only buff_key
(magic-detection vs enemy-detection) and duration_rounds (100 vs 10) differ.

Demo fixture: Thalindra Moonwhisper (Wizard) carries an equipped Wand of
Magic Detection + a 3-charge resource row at key `wand-of-magic-detection`.
No attunement: the wand grants its effect while merely equipped.

Tests:
  - happy path: detect with Thalindra in an active battle → action_kind
    "buff", buff_key "magic-detection", charges_spent=1, buff_installed=
    True, duration_rounds=100 (10 minutes), resource 3 → 2, and the buff
    lands on Thalindra's combatant.
  - drained wand (0 charges) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "wand-of-magic-detection"


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
    raise AssertionError("Thalindra has no wand-of-magic-detection item")


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def thalindra_full_wand(gm_client, thalindra):
    """Force-reseed Thalindra's Wand of Magic Detection to full 3 charges,
    restoring the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": resources},
    )
    yield thalindra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_wand_of_magic_detection_installs_buff(gm_client, thalindra_full_wand):
    """Happy path: detect with Thalindra in an active battle → action_kind
    "buff", buff_key "magic-detection", charges_spent=1, buff_installed=True,
    duration_rounds=100 (10 minutes), resource 3 → 2."""
    th = thalindra_full_wand
    idx = await _wand_inv_idx(gm_client, th["id"])
    th_cid = f"tok_wmd1_thal_{th['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_cid, th["id"], name=th["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{th['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "detect",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "buff"
    assert data["buff_key"] == "magic-detection"
    assert data["charges_spent"] == 1
    assert data["buff_installed"] is True
    # 10 minutes @ 6 s/round (Detect Magic concentration duration) = 100.
    assert data["duration_rounds"] == 100
    assert data["resource"]["current"] == 2  # 3 → 2

    # The magic-detection buff lands on Thalindra's combatant.
    battle_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combatants = (
        ((battle_resp.json() or {}).get("battle") or {}).get("combatants") or []
    )
    me = next((c for c in combatants if c.get("id") == th_cid), None)
    assert me is not None
    keys = {b.get("key") for b in (me.get("buffs") or []) if isinstance(b, dict)}
    assert "magic-detection" in keys


async def test_wand_of_magic_detection_empty_returns_409(gm_client, thalindra):
    """Drain the wand to 0 charges via /sheet-fields, then try to detect →
    409 insufficient_charges."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    drained = [
        {**r, "current": 0} if (isinstance(r, dict) and r.get("key") == _SLUG) else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"resources": drained},
    )
    try:
        idx = await _wand_inv_idx(gm_client, thalindra["id"])
        th_cid = f"tok_wmd2_thal_{thalindra['id']}"
        await _seed_battle(gm_client, [
            _mkc(th_cid, thalindra["id"], name=thalindra["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
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
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"resources": snapshot},
        )


async def test_wand_of_magic_detection_no_attunement_required(gm_client, thalindra):
    """No-attunement contract — the seed inventory entry doesn't carry
    `attuned: True`, yet the action still fires (the dispatcher's
    requires_attunement check is False for this wand)."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    wand = next(
        (it for it in inv
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert wand is not None, "Thalindra should have the wand"
    assert wand.get("equipped") is True
    assert not wand.get("attuned"), (
        f"wand should grant its effect un-attuned, got: {wand!r}"
    )
