"""v2.325.0 — Wand of Secrets (RAW DMG p.211, uncommon, NO attunement).
3 charges, regain 1d3 at dawn. Action: expend 1 charge → wand whispers
the distance and direction of any secret door or trap within 30 ft.
Direct clone of v2.324.0 Wand of Magic Detection's `action_kind: "buff"`
substrate — only buff_key (`secrets-detection`) and duration_rounds
(1 = single whisper per charge, vs Detect Magic's 100-round concentration)
differ.

Demo fixture: Pip Quickfingers (Halfling Rogue) carries an equipped Wand
of Secrets + a 3-charge resource row at key `wand-of-secrets`. No
attunement: the wand fires while merely equipped.

Tests:
  - happy path: reveal with Pip in an active battle → action_kind "buff",
    buff_key "secrets-detection", charges_spent=1, buff_installed=True,
    duration_rounds=1, resource 3 → 2, and the buff lands on Pip's
    combatant.
  - drained wand (0 charges) → 409 insufficient_charges.
  - no-attunement contract: the seed inventory item has `equipped: True`
    and no `attuned: True` flag.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "wand-of-secrets"


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
    raise AssertionError("Pip has no wand-of-secrets inventory item")


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


@pytest_asyncio.fixture
async def pip_full_wand(gm_client, pip):
    """Force-reseed Pip's Wand of Secrets to a full 3 charges, restoring
    the snapshot on teardown."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == _SLUG:
            resources[i] = {**r, "current": 3, "max": 3}
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


async def test_wand_of_secrets_installs_buff(gm_client, pip_full_wand):
    """Happy path: reveal with Pip in an active battle → action_kind "buff",
    buff_key "secrets-detection", charges_spent=1, buff_installed=True,
    duration_rounds=1, resource 3 → 2."""
    p = pip_full_wand
    idx = await _wand_inv_idx(gm_client, p["id"])
    p_cid = f"tok_wsec1_pip_{p['id']}"
    await _seed_battle(gm_client, [
        _mkc(p_cid, p["id"], name=p["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{p['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "reveal",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_kind"] == "buff"
    assert data["buff_key"] == "secrets-detection"
    assert data["charges_spent"] == 1
    assert data["buff_installed"] is True
    # Single-whisper per charge — 1-round duration (vs Detect Magic's 100).
    assert data["duration_rounds"] == 1
    assert data["resource"]["current"] == 2  # 3 → 2

    # The secrets-detection buff lands on Pip's combatant.
    battle_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combatants = (
        ((battle_resp.json() or {}).get("battle") or {}).get("combatants") or []
    )
    me = next((c for c in combatants if c.get("id") == p_cid), None)
    assert me is not None
    keys = {b.get("key") for b in (me.get("buffs") or []) if isinstance(b, dict)}
    assert "secrets-detection" in keys


async def test_wand_of_secrets_empty_returns_409(gm_client, pip):
    """Drain the wand to 0 charges via /sheet-fields, then try to reveal →
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
        p_cid = f"tok_wsec2_pip_{pip['id']}"
        await _seed_battle(gm_client, [
            _mkc(p_cid, pip["id"], name=pip["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "reveal",
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


async def test_wand_of_secrets_no_attunement_required(gm_client, pip):
    """No-attunement contract — the seed inventory entry doesn't carry
    `attuned: True`, yet the action still fires (the dispatcher's
    requires_attunement check is False for this wand)."""
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = sheet.get("inventory") or []
    wand = next(
        (it for it in inv
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert wand is not None, "Pip should have the wand"
    assert wand.get("equipped") is True
    assert not wand.get("attuned"), (
        f"wand should grant its effect un-attuned, got: {wand!r}"
    )
