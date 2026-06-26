"""v2.99.235 — Tempest Domain Cleric: Wrath of the Storm (Phase H.1 second domain).

Phase H.1 second non-Life Cleric domain ship. RAW PHB p.62:
Tempest Lv 1 reaction — when a creature within 5 ft hits you,
target DEX save DC 8 + prof + WIS mod or take 2d8 lightning /
thunder. Uses per long rest = WIS mod (min 1).

v1 ships:
  - /use_wrath_of_the_storm: validates Tempest Cleric Lv 1+ +
    wrath-of-the-storm resource current >= 1 + reaction chip;
    decrements counter; rolls 2d8 server-side; computes DC;
    broadcasts feature_used (source wrath-of-the-storm) with
    (damage, damage_type, save_dc, attacker_name, uses_remaining).

**v2.673.0 (Phase 8):** when `attacker_combatant_id` resolves to a
sheet, the attacker's DEX save is rolled + the 2d8 applied server-
side (full on fail, half on success) via `_apply_damage_to_combatant`
(`is_magical=True`); a free-form `attacker_name` alone stays
announce-only.

Brother Tavik Stonebrow is the demo fixture; tests PATCH his
subclass to "Tempest Domain" + seed a wrath-of-the-storm
resource via sheet.resources PATCH.

Tests:
  - Happy lightning → uses 3 → 2, damage in 2..16, DC 14
    (Tavik Lv 8: prof +3 + WIS +3).
  - Apply: templated bandit attacker → DEX save rolled + 2d8 applied.
  - Announce-only: free-form attacker_name → no save/damage applied.
  - Thunder mode → damage_type "thunder" in broadcast.
  - Bad damage_type → 400.
  - Out of uses (current 0) → 409.
  - Wrong subclass (default Life) → 409.
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


def _wots_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "wrath-of-the-storm"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _wots_resource(current: int, maximum: int) -> dict:
    return {
        "key": "wrath-of-the-storm",
        "name": "Wrath of the Storm",
        "current": current, "max": maximum, "reset": "long",
        "source": "cleric Lv 1 / Tempest Domain",
        "class_slug": "cleric",
        "desc": "Reaction: when hit by a melee attacker within 5 ft, target makes Dex save or take 2d8 lightning/thunder. WIS mod uses per long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def tavik_tempest_domain(gm_client, roster):
    """PATCH Tavik to Tempest Domain + seed wrath-of-the-storm
    resource with 3 uses. Seed him in a battle so reaction chip
    has a home."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": "Tempest Domain",
            "resources": [_wots_resource(3, 3)],
        },
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wots_{tavik['id']}",
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


async def test_use_wots_lightning_happy(
    gm_client, gm_ws, tavik_tempest_domain,
):
    """Tempest Tavik → uses 3 → 2, damage 2..16, DC 14, broadcast."""
    tavik = tavik_tempest_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "lightning",
            "attacker_name": "Bandit Beta",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 2 <= data["damage"] <= 16
    assert data["damage_type"] == "lightning"
    assert data["save_dc"] == 14, data  # prof 3 + WIS 3 = 14
    assert data["uses_remaining"] == 2
    await asyncio.sleep(0.3)
    feats = _wots_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_wots_applies_damage_to_attacker(
    gm_client, tavik_tempest_domain,
):
    """v2.673.0 — Phase 8: a templated NPC attacker now has its DEX save
    rolled + the 2d8 applied server-side. Re-seed the battle with Tavik + a
    real bandit *template*, then assert save resolution + applied amount
    consistent with the outcome (vanilla bandit → no lightning resistance →
    exact)."""
    tavik = tavik_tempest_domain
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wots_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_wots_bandit", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "lightning",
            "attacker_combatant_id": "tok_wots_bandit",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_total"] is not None, data
    assert isinstance(data["save_passed"], bool), data
    applied = data["damage_applied"]
    assert applied is not None, data
    expected = (data["damage"] // 2) if data["save_passed"] else data["damage"]
    assert applied == expected, data


async def test_wots_no_combatant_announce_only(
    gm_client, tavik_tempest_domain,
):
    """v2.673.0 — a free-form attacker_name (no combatant id) stays
    backward-compatible announce-only: no save rolled, no damage applied."""
    tavik = tavik_tempest_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "thunder",
            "attacker_name": "Some Goblin",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_total"] is None
    assert data["save_passed"] is None
    assert data["damage_applied"] is None


async def test_use_wots_thunder(
    gm_client, tavik_tempest_domain,
):
    """damage_type = thunder → broadcast carries it."""
    tavik = tavik_tempest_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "thunder",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["damage_type"] == "thunder"


async def test_use_wots_bad_damage_type(
    gm_client, tavik_tempest_domain,
):
    """damage_type = 'fire' → 400."""
    tavik = tavik_tempest_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "fire",
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_wots_out_of_uses(
    gm_client, tavik_tempest_domain,
):
    """current=0 → 409 out_of_uses."""
    tavik = tavik_tempest_domain
    await _patch_sheet(
        gm_client, tavik["id"],
        {"resources": [_wots_resource(0, 3)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "lightning",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_wots_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wrath_of_the_storm",
        json={
            "character_id": tavik["id"],
            "damage_type": "lightning",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
