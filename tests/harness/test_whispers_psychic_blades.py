"""v2.99.322 — Whispers College Bard: Psychic Blades (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #4. RAW XGE p.17: on weapon hit,
expend 1 BI use to deal extra psychic damage.

Damage by bard level:
- Lv 3-4: 2d6
- Lv 5-9: 3d6
- Lv 10-14: 5d6
- Lv 15+: 8d6

Endpoint slug `/use_whispers_psychic_blades` to avoid collision
with Soulknife Rogue's `/use_psychic_blades` (v2.99.311).

v1 announce-only — BI decrement via existing flow.

Lyra Lv 6 → 3d6 psychic.

Tests:
  - Lv 6 happy → 3d6 psychic.
  - Lv 10 → 5d6.
  - Lv 15 → 8d6.
  - Wrong subclass → 409.
  - Whispers Lv 2 → 409.
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


def _wpb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "whispers-psychic-blades"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_whispers(gm_client, roster):
    """PATCH Lyra to College of Whispers."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Whispers"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_wpb_happy_lv6(
    gm_client, gm_ws, lyra_whispers,
):
    """Lv 6 Whispers → 3d6 psychic."""
    lyra = lyra_whispers
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "3d6"
    assert data["damage_type"] == "psychic"
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _wpb_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_wpb_lv10(
    gm_client, lyra_whispers,
):
    """Lv 10 → 5d6."""
    lyra = lyra_whispers
    await _patch_sheet(
        gm_client, lyra["id"], {"level": 10},
        class_slug="bard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "5d6"


async def test_use_wpb_lv15(
    gm_client, lyra_whispers,
):
    """Lv 15 → 8d6."""
    lyra = lyra_whispers
    await _patch_sheet(
        gm_client, lyra["id"], {"level": 15},
        class_slug="bard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "8d6"


async def test_wpb_applies_psychic_damage_to_target(
    gm_client, lyra_whispers,
):
    """v2.668.0 — Phase 8: with a `target_combatant_id`, Psychic Blades now
    rolls the level-scaled NdN psychic server-side and applies it via
    `_apply_damage_to_combatant` (was announce-only). Lv 6 Lyra → 3d6.
    Seeds a battle with an NPC bandit (high HP) so the target resolves +
    survives; asserts the rolled amount is in 3..18 and the applied amount
    landed (accepting resistance halving)."""
    lyra = lyra_whispers
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    bandit_cid = "tok_wpb_bandit"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wpb_l_{lyra['id']}", "char_id": lyra["id"],
             "name": lyra["name"], "initiative": 11,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_cid, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 100, "hp_max": 100, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"], "target_combatant_id": bandit_cid},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "3d6"
    dr = data.get("damage_rolled")
    da = data.get("damage_applied")
    assert dr is not None and 3 <= dr <= 18, f"3d6 should roll 3..18; got {dr}"
    # psychic vs a vanilla bandit applies fully; accept resistance halving
    # defensively (residual shared-DB state) but it always lands ≥ 1 (min 3d6
    # = 3, halved = 1).
    assert da is not None and da > 0
    assert da in (dr, dr // 2), (
        f"applied should be rolled or halved; got rolled={dr}, applied={da}"
    )


async def test_use_wpb_no_target_announce_only(
    gm_client, lyra_whispers,
):
    """Backward-compatible: no `target_combatant_id` stays announce-only —
    no damage is rolled or applied."""
    lyra = lyra_whispers
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("damage_rolled") is None
    assert data.get("damage_applied") is None


async def test_use_wpb_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wpb_level_gate(
    gm_client, roster,
):
    """Whispers Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Whispers", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_whispers_psychic_blades",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )
