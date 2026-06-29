"""v2.745.0 — homebrew-monster "Parse from description" helper.

`POST /api/parse-monster-action` {desc} (authed) regex-extracts the structured
attack fields from a pasted SRD-style action description, so the homebrew
Actions editor can pre-fill To-hit / Damage / Type / Save DC instead of
requiring every field by hand. Stateless text parsing.
"""


async def test_parse_melee_attack(gm_client):
    r = await gm_client.post("/api/parse-monster-action", json={
        "desc": ("Melee Weapon Attack: +5 to hit, reach 5 ft., one target. "
                 "Hit: 7 (1d8 + 3) slashing damage.")})
    assert r.status_code == 200, r.text
    p = r.json()["parsed"]
    assert p["attack_roll"] is True
    assert p["attack_bonus"] == "+5"
    assert p["damage"] == "1d8+3"
    assert p["damage_type"] == "slashing"
    assert p["reach"] == "5 ft."
    assert p["save_dc"] is None


async def test_parse_save_breath_weapon(gm_client):
    r = await gm_client.post("/api/parse-monster-action", json={
        "desc": ("The dragon exhales fire. Each creature in a 60-foot cone "
                 "must make a DC 18 Dexterity saving throw, taking 56 (16d6) "
                 "fire damage on a failed save, or half as much on a success.")})
    assert r.status_code == 200, r.text
    p = r.json()["parsed"]
    assert p["save_dc"] == 18
    assert p["save_ability"] == "DEX"
    assert p["damage"] == "16d6"
    assert p["damage_type"] == "fire"
    # No attack roll for a save-based effect.
    assert p["attack_roll"] is False and p["attack_bonus"] == ""


async def test_parse_ranged_range_field(gm_client):
    r = await gm_client.post("/api/parse-monster-action", json={
        "desc": ("Ranged Weapon Attack: +4 to hit, range 80/320 ft., one "
                 "target. Hit: 5 (1d6 + 2) piercing damage.")})
    assert r.status_code == 200, r.text
    p = r.json()["parsed"]
    assert p["range"] == "80/320 ft."
    assert p["attack_bonus"] == "+4"


async def test_parse_empty_desc_400(gm_client):
    r = await gm_client.post("/api/parse-monster-action", json={"desc": "   "})
    assert r.status_code == 400, r.text
