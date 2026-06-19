"""Identify — L1 divination ritual, Bard/Wizard.
Phase 2 #16 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.459.0 — RAW PHB p.252: "You choose one object that you must
touch throughout the casting of the spell. If it is a magic item
or some other magic-imbued object, you learn its properties and
how to use them, whether it requires attunement to use, and how
many charges it has, if any. You learn whether any spells are
affecting the item and what they are. If the item was created
by a spell, you learn which spell created it. If you instead
touch a creature throughout the casting, you learn what spells,
if any, are currently affecting it." 1 minute (ritual), V/S/M
(pearl worth 100 gp + owl feather), Touch, Instantaneous.

**First non-buff cast in the Phase 2 arc.** Identify is RAW-
instantaneous — no buff installed, no duration to track. The
endpoint broadcasts a `feature_used` card naming what's being
identified; the GM types the learned properties in chat.

Tests:
  - Cast with target_item_name → broadcast carries the item
    name; no `identify` buff is installed on the caster.
  - Cast with target_character_id → broadcast carries target id
    and resolved target name.
  - Cast with no target → broadcast still fires with both
    target fields null.
  - Krieger (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_id_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_identify_on_item_no_buff_installed(gm_client, roster):
    """Wizard casts Identify on a named item; response echoes the
    item name and NO identify buff is installed (RAW
    instantaneous)."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_identify",
        json={
            "character_id": wiz["id"],
            "target_item_name": "mysterious gauntlet",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "identify"
    assert body["target_item_name"] == "mysterious gauntlet"
    assert body["target_character_id"] is None

    # First non-buff cast in the arc — verify no Identify-keyed
    # buff was installed.
    buffs = await _get_buffs(gm_client, wiz["id"])
    assert not any(
        b.get("key") == "identify" for b in buffs
    ), f"no identify buff expected (instantaneous spell); got {buffs}"


async def test_cast_identify_on_creature_echoes_target(gm_client, roster):
    """Cast on a target_character_id resolves the target's name
    and echoes both fields in the response."""
    wiz = roster["Thalindra Moonwhisper"]
    target = roster["Krieger Stonefist"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_identify",
        json={
            "character_id": wiz["id"],
            "target_character_id": target["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_character_id"] == target["id"]
    assert body["target_character_name"] == target["name"]
    assert body["target_item_name"] is None


async def test_cast_identify_with_no_target_still_broadcasts(
    gm_client, roster,
):
    """Cast with neither target_character_id nor target_item_name
    still succeeds; broadcast/response carry null target fields."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_identify",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["target_character_id"] is None
    assert body["target_item_name"] is None


async def test_cast_identify_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast — Identify is
    Bard/Wizard only per RAW."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_identify",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "identify" in body["expected"].lower()
