"""v2.99.281 — Redemption Paladin: Aura of the Guardian (H.2 depth).

H.2 depth ship — Redemption's Lv 7 reactive damage-shield. RAW
XGE p.39: when a creature within 10 feet of you takes damage,
you can use your reaction to magically take that damage,
instead of that creature taking it. At Lv 18, the range
increases to 30 ft. This feature doesn't transfer any other
effects; this damage can't be reduced.

**v2.694.0 (Phase 8):** the damage-redirection swap is now applied
server-side (trust-the-caller — the ally already took the damage):
with `ally_combatant_id` + `damage_amount`, the ally is healed back by
that amount and the Paladin takes it (untyped, unreducible). Response
gains `redirected` / `ally_healed` / `paladin_damage_applied`.
Costs a reaction chip.

Caelan Lv 7 → radius 10. Tests PATCH his subclass to
"Oath of Redemption".

Tests:
  - Lv 7 happy → radius 10, reaction chip marked.
  - Redirect: wounded NPC ally healed back + Paladin takes the damage.
  - Announce-only: no redirect args → redirected False.
  - Lv 18 happy → radius 30 (RAW upgrade).
  - Wrong subclass → 409.
  - Level gate (Lv 6) → 409.
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


def _aotg_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-the-guardian"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_redemption_lv7(gm_client, roster):
    """PATCH Caelan to Redemption. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption"},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_aotg_happy_lv7(
    gm_client, gm_ws, caelan_redemption_lv7,
):
    """Lv 7 Redemption → radius 10."""
    caelan = caelan_redemption_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _aotg_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_aotg_redirects_damage(
    gm_client, caelan_redemption_lv7,
):
    """v2.694.0 — Phase 8: the redirection heals the ally back + transfers the
    damage to the Paladin. Seed Caelan + a wounded NPC ally (10/50, 40
    headroom), set Caelan to a high known HP, then redirect 8 damage."""
    caelan = caelan_redemption_lv7
    # Give Caelan headroom so the redirected damage doesn't drop him to 0.
    await _patch_sheet(
        gm_client, caelan["id"], {"hp": {"current": 50}},
    )
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_aotg_{caelan['id']}", "char_id": caelan["id"],
             "name": caelan["name"], "initiative": 12,
             "hp_current": 50, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_aotg_ally", "char_id": None,
             "token_template_id": bandit["id"], "name": "Wounded Ally",
             "initiative": 8, "hp_current": 10, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
        json={"character_id": caelan["id"], "override": True,
              "ally_combatant_id": "tok_aotg_ally", "damage_amount": 8},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["redirected"] is True, data
    # Ally had 40 headroom → full heal-back; untyped → full damage to Caelan.
    assert data["ally_healed"] == 8, data
    assert data["paladin_damage_applied"] == 8, data


async def test_aotg_no_redirect_announce_only(
    gm_client, caelan_redemption_lv7,
):
    """v2.694.0 — no redirect args → backward-compatible announce-only."""
    caelan = caelan_redemption_lv7
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["redirected"] is False
    assert data["ally_healed"] is None
    assert data["paladin_damage_applied"] is None


async def test_use_aotg_lv18_radius_upgrade(
    gm_client, caelan_redemption_lv7,
):
    """Lv 18 → radius 30 (RAW upgrade)."""
    caelan = caelan_redemption_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 30
    assert data["paladin_level"] == 18


async def test_use_aotg_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aotg_level_gate(
    gm_client, roster,
):
    """Redemption Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_the_guardian",
            json={"character_id": caelan["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )
