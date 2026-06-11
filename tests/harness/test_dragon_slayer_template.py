"""v2.158.98 — magic-items-automation Phase 6b: Young Red Dragon token
template carries ``sheet.type == "dragon"`` so the v2.97.48
``_attacker_creature_type`` helper (routed in via Phase 5f) auto-
resolves it without the battle PUT needing to set ``creature_type``
on the combatant. Validates the third resolution branch of the
helper (PC sheet branch covered by `test_dragon_slayer_helper.py`,
runtime override by `test_dragon_slayer_rider.py`).

Demo flow this unblocks: a GM drag-spawns the Young Red Dragon
template from the Templates drawer; the spawned token gets the
template's id via ``token_template_id``; Caelan attacks; Dragon
Slayer rider fires automatically with no test-style PUT plumbing.

Test method: GET /templates → find the Young Red Dragon → PUT a
battle with a combatant referencing it via ``token_template_id`` (no
``creature_type`` on the combatant), then POST /attack and assert
the rider fires.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_DRAGON_SLAYER_ATTACK_IDX = 2


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


@pytest_asyncio.fixture
async def young_red_dragon_template_id(gm_client):
    """v2.158.98: the demo seed ships a Young Red Dragon token
    template with ``sheet.type: "dragon"``. Look up its id via the
    templates list endpoint so the test can wire it into the battle
    PUT without hardcoding."""
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert resp.status_code == 200, resp.text
    templates = resp.json()
    for t in templates:
        if t["name"] == "Young Red Dragon":
            assert (t["sheet"] or {}).get("type") == "dragon", (
                f"Young Red Dragon template should carry sheet.type='dragon'; "
                f"got {t['sheet']!r}"
            )
            return t["id"]
    raise AssertionError(
        f"No Young Red Dragon template in the demo seed. "
        f"Found: {[t['name'] for t in templates]}"
    )


async def test_dragon_slayer_fires_via_template_type(
    gm_client, caelan, young_red_dragon_template_id,
):
    """v2.158.98: combatant references the Young Red Dragon template
    via ``token_template_id`` but does NOT set ``creature_type`` on
    the combatant dict. The Phase 5f resolver shim looks up the
    template's ``sheet.type = "dragon"`` and injects it before
    invoking the Dragon Slayer condition predicate → rider fires.

    This is the path a real demo user hits when they drag-spawn the
    Young Red Dragon from the Templates drawer and Caelan attacks
    the resulting token."""
    caelan_cid = f"tok_dst1_caelan_{caelan['id']}"
    dragon_cid = "tok_dst1_yrd"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": caelan_cid,
                    "char_id": caelan["id"],
                    "name": caelan["name"],
                    "initiative": 10,
                    "hp_current": 200, "hp_max": 200, "ac": 18,
                    "buffs": [],
                    "speed_walk": 30,
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
                {
                    "id": dragon_cid,
                    "char_id": None,
                    "name": "Young Red Dragon",
                    "initiative": 8,
                    "hp_current": 178, "hp_max": 178, "ac": 1,
                    "buffs": [],
                    # NO creature_type field — exercise template branch.
                    "token_template_id": young_red_dragon_template_id,
                    "speed_walk": 40,
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
            "target_combatant_id": dragon_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Dragon Slayer Longsword"

    ups = _uplifts(data, "item-dragon-slayer")
    assert len(ups) == 1, (
        "Template-resolved creature_type=dragon must trigger the rider; "
        f"auto_uplifts={data.get('auto_uplifts')}"
    )
    assert ups[0]["damage_type"] == "slashing"
    assert ups[0]["expression"] == "3d6"
