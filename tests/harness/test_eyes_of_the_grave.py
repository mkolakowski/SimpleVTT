"""v2.99.241 — Grave Domain Cleric: Eyes of the Grave (Phase H.1 eighth domain).

Phase H.1 eighth non-Life Cleric domain ship. RAW XGE p.19:
Grave Cleric Lv 1+ action — detect undead within 60 ft for 1
round. WIS mod uses per long rest.

v1 ships:
  - /use_eyes_of_the_grave: validates Grave Cleric Lv 1+ +
    resource current >= 1 + action chip; decrements counter;
    marks chip; broadcasts feature_used (source
    eyes-of-the-grave).

Brother Tavik Stonebrow is the demo fixture; tests PATCH his
subclass to "Grave Domain" + seed an eyes-of-the-grave
resource.

Tests:
  - Happy → uses 3 → 2 + action chip + broadcast.
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


def _eotg_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "eyes-of-the-grave"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _eotg_resource(current: int, maximum: int) -> dict:
    return {
        "key": "eyes-of-the-grave",
        "name": "Eyes of the Grave",
        "current": current, "max": maximum, "reset": "long",
        "source": "cleric Lv 1 / Grave Domain",
        "class_slug": "cleric",
        "desc": "Action: detect undead within 60 ft for 1 round. WIS mod uses per long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def tavik_grave_domain(gm_client, roster):
    """PATCH Tavik to Grave Domain + seed resource + battle."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": "Grave Domain",
            "resources": [_eotg_resource(3, 3)],
        },
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_eg_{tavik['id']}",
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


async def test_use_eotg_happy(
    gm_client, gm_ws, tavik_grave_domain,
):
    """Grave Tavik → uses 3 → 2 + broadcast."""
    tavik = tavik_grave_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_grave",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 2
    await asyncio.sleep(0.3)
    feats = _eotg_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_eotg_out_of_uses(
    gm_client, tavik_grave_domain,
):
    """current=0 → 409."""
    tavik = tavik_grave_domain
    await _patch_sheet(
        gm_client, tavik["id"],
        {"resources": [_eotg_resource(0, 3)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_grave",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_eotg_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eyes_of_the_grave",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
