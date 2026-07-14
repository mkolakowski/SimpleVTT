"""v2.1017.0 — Nature's Sanctuary (Circle of the Land Druid Lv 14+).

PHB p.69: "When a beast or plant creature attacks you, that creature
must make a Wisdom saving throw against your druid spell save DC. On a
failed save, the creature must choose a different target, or the attack
automatically misses." Circle of the Land is the SRD druid circle, so
this is SRD-valid. Mira Greenleaf (Druid Circle of the Moon Lv 5) is the
demo fixture, PATCH'd to Circle of the Land Lv 14 (subclass + level).

The endpoint installs a `natures-sanctuary` buff on the druid; the
`/npc_attack` gate reads it and, when the attacker's creature type is
beast/plant, rolls the attacker's WIS save — on a fail the attack
automatically misses (`natures_sanctuary_blocked`).

Tests:
  - Install → a `natures-sanctuary` buff with `effects.dc`.
  - A beast attacker vs the warded druid is blocked (loop until a
    failed save lands; the gate fires).
  - A humanoid attacker is NEVER blocked (creature-type restriction).
  - Level gate: Mira as Moon Lv 5 → 409.
  - Error paths: missing character_id → 400; unknown char → 404.
"""
import asyncio

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


def _pc(cid, c, *, hp_max=120):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


def _npc(cid, name, *, creature_type, hp=40):
    return {"id": cid, "char_id": None, "name": name,
            "creature_type": creature_type,
            "initiative": 5, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, mira, beast_id, humanoid_id):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_ns_mira_{mira['id']}", mira),
            _npc(beast_id, "Dire Wolf", creature_type="beast"),
            _npc(humanoid_id, "Bandit", creature_type="humanoid"),
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _install(gm_client, mira):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_sanctuary",
        json={"character_id": mira["id"]},
    )


async def _ns_buff(gm_client, char_id):
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )).json().get("buffs", [])
    return next(
        (b for b in buffs if (b or {}).get("key") == "natures-sanctuary"),
        None,
    )


async def _npc_attack(gm_client, attacker_id, target_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": attacker_id,
            "action_name": "Bite",
            "attack_bonus": "+5",
            "damage": "2d6+3",
            "damage_type": "piercing",
            "range": "5 ft",
            "target_combatant_id": target_id,
            "override_range": True,
        },
    )


async def test_natures_sanctuary_installs_buff(gm_client, roster):
    """Mira PATCH'd to Land Lv 14 → a natures-sanctuary buff with a DC."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(gm_client, mira["id"],
                       {"level": 14, "subclass": "Circle of the Land"},
                       class_slug="druid")
    try:
        await _seed(gm_client, mira, f"ns_beast_{mira['id']}",
                    f"ns_hum_{mira['id']}")
        r = await _install(gm_client, mira)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["buff_installed"] is True
        assert data["save_dc"] >= 8
        await asyncio.sleep(0.2)
        buff = await _ns_buff(gm_client, mira["id"])
        assert buff is not None
        assert (buff.get("effects") or {}).get("dc") == data["save_dc"]
    finally:
        await _patch_sheet(gm_client, mira["id"],
                           {"level": 5, "subclass": "Circle of the Moon"},
                           class_slug="druid")


async def test_natures_sanctuary_blocks_beast_attack(gm_client, roster):
    """A beast attacking the warded druid must WIS-save; on a fail the
    attack is blocked. Loop until a block lands (save mod 0 vs a high DC
    → mostly fails)."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(gm_client, mira["id"],
                       {"level": 14, "subclass": "Circle of the Land"},
                       class_slug="druid")
    try:
        beast_id = f"ns_beast2_{mira['id']}"
        hum_id = f"ns_hum2_{mira['id']}"
        mira_cid = f"tok_ns_mira_{mira['id']}"
        await _seed(gm_client, mira, beast_id, hum_id)
        await _install(gm_client, mira)
        blocked_seen = False
        for _ in range(20):
            r = await _npc_attack(gm_client, beast_id, mira_cid)
            assert r.status_code == 200, r.text
            if r.json().get("natures_sanctuary_blocked"):
                blocked_seen = True
                assert r.json()["hit"] is False
                break
        assert blocked_seen, (
            "a beast attacker never failed the Nature's Sanctuary save "
            "in 20 tries"
        )
    finally:
        await _patch_sheet(gm_client, mira["id"],
                           {"level": 5, "subclass": "Circle of the Moon"},
                           class_slug="druid")


async def test_natures_sanctuary_ignores_humanoid(gm_client, roster):
    """A humanoid attacker is never blocked (beast/plant restriction)."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(gm_client, mira["id"],
                       {"level": 14, "subclass": "Circle of the Land"},
                       class_slug="druid")
    try:
        beast_id = f"ns_beast3_{mira['id']}"
        hum_id = f"ns_hum3_{mira['id']}"
        mira_cid = f"tok_ns_mira_{mira['id']}"
        await _seed(gm_client, mira, beast_id, hum_id)
        await _install(gm_client, mira)
        for _ in range(10):
            r = await _npc_attack(gm_client, hum_id, mira_cid)
            assert r.status_code == 200, r.text
            assert not r.json().get("natures_sanctuary_blocked"), (
                "a humanoid attacker must NOT be blocked by Nature's "
                "Sanctuary"
            )
    finally:
        await _patch_sheet(gm_client, mira["id"],
                           {"level": 5, "subclass": "Circle of the Moon"},
                           class_slug="druid")


async def test_natures_sanctuary_level_gate(gm_client, roster):
    """Mira as Circle of the Moon Lv 5 → 409 (needs Land Lv 14)."""
    mira = roster["Mira Greenleaf"]
    r = await _install(gm_client, mira)
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_natures_sanctuary_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_sanctuary",
        json={},
    )
    assert r.status_code == 400, r.text


async def test_natures_sanctuary_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_natures_sanctuary",
        json={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
