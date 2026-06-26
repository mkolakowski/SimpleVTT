"""v2.99.358 — Way of Mercy Monk: Hands of Healing (G Monk Ways batch #4, Lv 3+, TCE).

Phase G Monk Ways subclass batch ship #4 — Way of Mercy opens.
RAW TCE p.51: as an action, spend 1 ki to touch a creature and
restore HP = a roll of your Martial Arts die + your WIS modifier.

**v2.674.0 (Phase 8):** the heal is now applied to a
`target_combatant_id` via `_apply_heal_to_combatant` (caps at max
HP, revives a dying PC); no target → backward-compatible announce-
only. The heal is rolled server-side. Action chip + 1 ki.

Kael Brightleaf (Monk, PATCHed to Way of Mercy Lv 7) is the demo
fixture (Martial Arts die 1d6 at Lv 5-10).

Tests:
  - Lv 7 happy: heal = max(1, 1d6 + WIS mod), die 1d6, 1 ki spent.
  - Apply: wounded NPC target → heal_applied == heal_amount.
  - Announce-only: no target → heal_applied/revived stay None.
  - Wrong subclass (default Way of the Open Hand) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _hh_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hands-of-healing"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_mercy(gm_client, roster):
    """PATCH Kael to Way of Mercy + long-rest (full ki); restore
    to Way of the Open Hand on teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of Mercy"},
        class_slug="monk",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_hh_happy_lv7(
    gm_client, gm_ws, kael_mercy,
):
    """Lv 7 Way of Mercy → heal = max(1, 1d6 + WIS), 1 ki spent."""
    kael = kael_mercy
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hands_of_healing",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "hands-of-healing"
    assert data["martial_arts_die"] == "1d6"
    assert 1 <= data["die_roll"] <= 6
    assert data["heal_amount"] == max(1, data["die_roll"] + data["wis_mod"])
    assert data["ki_spent"] == 1
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _hh_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["heal_amount"] == data["heal_amount"]


async def test_hh_applies_heal_to_target(
    gm_client, kael_mercy,
):
    """v2.674.0 — Phase 8: a wounded NPC target now has the rolled heal
    applied server-side via `_apply_heal_to_combatant`. Seed Kael + a bandit
    at 10/50 HP (lots of headroom so a small 1d6+WIS heal lands in full)."""
    kael = kael_mercy
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hh_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 12,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_hh_ally", "char_id": None,
             "token_template_id": bandit["id"], "name": "Wounded Ally",
             "initiative": 8, "hp_current": 10, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hands_of_healing",
        json={"character_id": kael["id"], "override": True,
              "target_combatant_id": "tok_hh_ally"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 40 headroom on the target → the full heal lands.
    assert data["heal_applied"] == data["heal_amount"], data
    assert data["revived"] is False


async def test_hh_no_target_announce_only(
    gm_client, kael_mercy,
):
    """v2.674.0 — no target → backward-compatible announce-only."""
    kael = kael_mercy
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hands_of_healing",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_applied"] is None
    assert data["revived"] is None


async def test_use_hh_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hands_of_healing",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_hh_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hands_of_healing",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
