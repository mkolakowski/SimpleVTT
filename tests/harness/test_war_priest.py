"""v2.99.236 — War Domain Cleric: War Priest (Phase H.1 third domain).

Phase H.1 third non-Life Cleric domain ship. RAW PHB p.63: War
Cleric Lv 1+ "when you use the Attack action, you can make one
weapon attack as a bonus action." Uses per long rest = WIS mod.

v1 ships:
  - /use_war_priest: validates War Cleric Lv 1+ + war-priest
    resource current >= 1 + bonus chip; decrements; marks chip;
    broadcasts. The bonus-action weapon attack itself is rolled
    via the normal /attack path.

Brother Tavik Stonebrow is the demo fixture; tests PATCH his
subclass to "War Domain" + seed a war-priest resource.

Tests:
  - Happy → uses 3 → 2, bonus chip marked, broadcast.
  - Out of uses → 409.
  - Wrong subclass → 409.
"""
import asyncio
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


def _wp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "war-priest"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _wp_resource(current: int, maximum: int) -> dict:
    return {
        "key": "war-priest",
        "name": "War Priest",
        "current": current, "max": maximum, "reset": "long",
        "source": "cleric Lv 1 / War Domain",
        "class_slug": "cleric",
        "desc": "Bonus action: one weapon attack after the Attack action. WIS mod uses per long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def tavik_war_domain(gm_client, roster):
    """PATCH Tavik to War Domain + seed war-priest resource + put
    him in a battle so the bonus chip mark succeeds."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": "War Domain",
            "resources": [_wp_resource(3, 3)],
        },
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wp_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "resources": []},
            class_slug="cleric",
        )


async def test_use_war_priest_happy(
    gm_client, gm_ws, tavik_war_domain,
):
    """War Cleric Tavik → uses 3 → 2 + bonus chip + broadcast."""
    tavik = tavik_war_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_priest",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 2
    await asyncio.sleep(0.3)
    feats = _wp_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_war_priest_out_of_uses(
    gm_client, tavik_war_domain,
):
    """current=0 → 409."""
    tavik = tavik_war_domain
    await _patch_sheet(
        gm_client, tavik["id"],
        {"resources": [_wp_resource(0, 3)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_priest",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_war_priest_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_priest",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
