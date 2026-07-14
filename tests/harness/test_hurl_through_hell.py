"""v2.1011.0 — Hurl Through Hell (The Fiend Warlock Lv 14+, PHB p.110).

"Once per turn when you hit a creature with an attack, you can use this
feature to instantly transport the target through the lower planes. ...
At the end of your next turn, the target ... takes 10d10 psychic damage
... unless the target is a fiend. Once you use this feature, you can't
use it again until you finish a long rest."

The Fiend is the SRD warlock patron, so Hurl Through Hell is SRD-valid.
Magnus Hexbinder (Warlock The Fiend Lv 5) is the demo fixture, PATCH'd
to Lv 14 for the happy paths (the endpoint auto-bootstraps the
1/long-rest resource).

Tests:
  - Happy path: Magnus@Lv14 hurls a non-fiend → 10d10 psychic applied,
    use consumed, broadcast.
  - Fiend exemption: a target flagged creature_type=fiend takes 0.
  - Out of uses: a second hurl before a long rest → 409.
  - Level gate: Magnus@Lv5 → 409.
  - Error paths: missing character_id → 400; missing target → 400;
    unknown char → 404.
"""
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


def _npc(cid, name, *, hp=200, creature_type=None):
    d = {"id": cid, "char_id": None, "name": name,
         "initiative": 5, "hp_current": hp, "hp_max": hp, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}}
    if creature_type is not None:
        d["creature_type"] = creature_type
    return d


async def _seed(gm_client, magnus, *, target):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_hth_magnus_{magnus['id']}", magnus),
            target,
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_hurl_through_hell_damages_non_fiend(gm_client, roster):
    """Magnus@Lv14 hurls a humanoid bandit → 10d10 psychic (10-100)
    applied, target not a fiend, and the single use is consumed."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 14},
                       class_slug="warlock")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        target_id = f"tok_hth_bandit_{magnus['id']}"
        await _seed(gm_client, magnus, target=_npc(target_id, "Bandit"))
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
            json={"character_id": magnus["id"],
                  "target_combatant_id": target_id},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["target_is_fiend"] is False
        assert 10 <= data["damage_rolled"] <= 100
        assert data["damage_applied"] > 0
        assert data["uses_remaining"] == 0
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_hurl_through_hell_exempts_fiend(gm_client, roster):
    """A target flagged creature_type=fiend takes no damage (RAW)."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 14},
                       class_slug="warlock")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        target_id = f"tok_hth_imp_{magnus['id']}"
        await _seed(gm_client, magnus,
                    target=_npc(target_id, "Imp", creature_type="fiend"))
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
            json={"character_id": magnus["id"],
                  "target_combatant_id": target_id},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["target_is_fiend"] is True
        assert data["damage_rolled"] == 0
        assert data["damage_applied"] == 0
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_hurl_through_hell_once_per_long_rest(gm_client, roster):
    """A second hurl before a long rest → 409 out_of_uses."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 14},
                       class_slug="warlock")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        target_id = f"tok_hth_b2_{magnus['id']}"
        await _seed(gm_client, magnus, target=_npc(target_id, "Bandit"))
        r1 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
            json={"character_id": magnus["id"],
                  "target_combatant_id": target_id},
        )
        assert r1.status_code == 200, r1.text
        r2 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
            json={"character_id": magnus["id"],
                  "target_combatant_id": target_id},
        )
        assert r2.status_code == 409, r2.text
        assert r2.json().get("error") == "out_of_uses"
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_hurl_through_hell_level_gate(gm_client, roster):
    """Magnus at Lv 5 → 409 (Hurl Through Hell needs Lv 14)."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
        json={"character_id": magnus["id"],
              "target_combatant_id": "tok_whatever"},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_hurl_through_hell_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
        json={"target_combatant_id": "tok_x"},
    )
    assert r.status_code == 400, r.text


async def test_hurl_through_hell_missing_target(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 400, r.text


async def test_hurl_through_hell_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hurl_through_hell",
        json={"character_id": 99999999, "target_combatant_id": "tok_x"},
    )
    assert r.status_code == 404, r.text
