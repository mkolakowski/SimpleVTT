"""v2.99.234 — Light Domain Cleric: Warding Flare (Phase H.1 first ship).

Phase H.1 first ship of the v2.99.193 phased completion plan
(non-Life Cleric domain coverage on the road to 3.0.0). RAW PHB
p.60: Lv 1 reaction — when attacked by a creature within 30 ft
you can see, impose disadvantage. Uses per long rest = WIS mod
(min 1). Attackers immune to blinded are immune.

v1 ships:
  - /use_warding_flare: validates Light Cleric Lv 1+ +
    warding-flare resource current >= 1 + reaction chip;
    decrements counter; marks chip; broadcasts feature_used
    (source warding-flare) with (attacker_name, uses_remaining).

Tavik Lightbringer (Cleric Life Domain Lv 8 default, WIS 16 →
+3 uses) is the demo fixture. Tests PATCH his subclass to
"Light Domain" + seed a warding-flare resource via
sheet.resources PATCH.

Tests:
  - Happy path → uses 3 → 2 + reaction chip + broadcast.
  - Out of uses (current 0) → 409 out_of_uses.
  - Wrong subclass (default Life) → 409.
  - Level gate (Lv 0) is impossible (Cleric min is 1); replaced
    with no-resource path → 404.
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


def _wf_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "warding-flare"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _warding_flare_block(current: int, maximum: int) -> dict:
    return {
        "key": "warding-flare",
        "name": "Warding Flare",
        "current": current, "max": maximum, "reset": "long",
        "source": "cleric Lv 1 / Light Domain",
        "class_slug": "cleric",
        "desc": "Reaction: impose disadvantage on an attacker within 30 ft you can see. WIS mod uses per long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def tavik_light_domain(gm_client, roster):
    """PATCH Tavik to Light Domain + seed warding-flare resource
    with 3 uses (WIS 16 → +3 mod)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": "Light Domain",
            "resources": [_warding_flare_block(3, 3)],
        },
        class_slug="cleric",
    )
    # Seed Tavik in a battle so the reaction chip mark succeeds.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wf_{tavik['id']}",
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


async def test_use_warding_flare_happy(
    gm_client, gm_ws, tavik_light_domain,
):
    """Light Cleric Tavik → uses 3 → 2 + broadcast."""
    tavik = tavik_light_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_warding_flare",
        json={
            "character_id": tavik["id"],
            "attacker_name": "Bandit Alpha",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 2
    await asyncio.sleep(0.3)
    feats = _wf_broadcasts(gm_ws, tavik["id"])
    assert feats
    assert feats[-1]["data"]["attacker_name"] == "Bandit Alpha"


async def test_use_warding_flare_out_of_uses(
    gm_client, tavik_light_domain,
):
    """current=0 → 409 out_of_uses."""
    tavik = tavik_light_domain
    await _patch_sheet(
        gm_client, tavik["id"],
        {"resources": [_warding_flare_block(0, 3)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_warding_flare",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_warding_flare_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_warding_flare",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_warding_flare_no_resource(
    gm_client, roster,
):
    """Light Cleric without the warding-flare resource entry
    → 404 (no Warding Flare resource on this sheet)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "resources": []},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_warding_flare",
            json={"character_id": tavik["id"], "override": True},
        )
        assert r.status_code == 404, r.text
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "resources": []},
            class_slug="cleric",
        )
