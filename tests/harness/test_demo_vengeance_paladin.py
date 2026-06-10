"""v2.158.56 — Demo Vengeance Paladin (Dame Seraphine Vael) seed contract.

v2.158.55 wired the Vow of Enmity sheet button (Vengeance Paladin
Lv 3+ Channel Divinity → /use_vow_of_enmity) into the Channel
Divinity resource-pill picker, but no demo PC was a Vengeance
Paladin — Sir Caelan is Oath of Devotion, whose CD options filter
Vow of Enmity out. This commit adds Dame Seraphine Vael (Oath of
Vengeance Lv 3) so the button is reachable + verifiable in the live
demo.

These tests assert the seed shape the picker filter depends on, then
fire /use_vow_of_enmity against the REAL seeded PC (no PATCH) — unlike
test_vow_of_enmity.py which PATCHes Caelan into Vengeance.

Tests:
  - Seed contract: the PC exists, is Paladin / Oath of Vengeance Lv 3,
    and carries a channel-divinity resource with subclass_slug
    "vengeance" (the field the picker class+subclass filter reads).
  - Happy path: with the CD reset to 1 and a target in battle,
    /use_vow_of_enmity decrements CD 1 → 0, installs the buff, and
    broadcasts feature_used(source=vow-of-enmity).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PC_NAME = "Dame Seraphine Vael"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json"
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def test_demo_vengeance_paladin_seed_contract(gm_client, roster):
    """The seeded PC is a Lv 3 Oath of Vengeance Paladin with a
    channel-divinity resource tagged subclass_slug=vengeance — the
    exact shape the CD picker filter needs to surface Vow of Enmity."""
    assert PC_NAME in roster, f"{PC_NAME} missing from demo roster"
    pc = roster[PC_NAME]
    sheet = await _sheet(gm_client, pc["id"])

    assert (sheet.get("class") or "").lower() == "paladin"
    assert (sheet.get("subclass") or "").lower() == "oath of vengeance"
    assert int(sheet.get("level") or 0) == 3

    cd = next(
        (r for r in (sheet.get("resources") or [])
         if (r.get("key") or "").lower() == "channel-divinity"),
        None,
    )
    assert cd is not None, "seed should carry a channel-divinity resource"
    assert (cd.get("subclass_slug") or "").lower() == "vengeance", (
        f"the picker filters CD options by subclass_slug; got {cd!r}"
    )


async def test_demo_vengeance_paladin_can_fire_vow(gm_client, gm_ws, roster):
    """End-to-end against the real seeded PC: reset CD to 1, seed a
    target in battle, fire /use_vow_of_enmity → 200, CD 1 → 0, buff
    installed, feature_used(source=vow-of-enmity) broadcast."""
    pc = roster[PC_NAME]
    # Reset CD to a known full charge so the test is idempotent across
    # a shared seeded session.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pc['id']}/sheet-fields",
        json={
            "class_slug": "paladin",
            "resources": [{
                "key": "channel-divinity",
                "name": "Channel Divinity",
                "current": 1, "max": 1, "reset": "short",
                "source": "paladin Lv 3",
                "class_slug": "paladin",
                "subclass_slug": "vengeance",
                "desc": "Channel an oath effect (Abjure Enemy, Vow of Enmity). One use per short rest.",
                "manual": False,
            }],
        },
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sv_{pc['id']}", "char_id": pc["id"], "name": pc["name"],
             "initiative": 12, "hp_current": 28, "hp_max": 28, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_sv_bandit", "char_id": None, "name": "Bandit Quarry",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vow_of_enmity",
        json={
            "character_id": pc["id"],
            "target_combatant_id": "tok_sv_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 0
    assert data["buff_installed"] is True
    assert data["target_name"] == "Bandit Quarry"

    await asyncio.sleep(0.3)
    feats = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "vow-of-enmity"
        and (m.get("data") or {}).get("character_id") == pc["id"]
    ]
    assert feats, "expected a feature_used(source=vow-of-enmity) broadcast"
