"""v2.99.229 — Wild Magic Sorcerer: Bend Luck (Phase 3).

Phase E.6 Phase 3 of the v2.99.193 phased completion plan. RAW
PHB p.103: "Starting at 6th level, you have the ability to
twist fate using your wild magic. When another creature you can
see makes an attack roll, an ability check, or a saving throw,
you can use your reaction and spend 2 sorcery points to roll
1d4 and apply the number rolled as a bonus or penalty to the
creature's roll."

v1 ships:
  - /use_bend_luck: validates Wild Magic Lv 6+ + 2 SP + reaction
    chip; decrements SP; rolls 1d4; broadcasts.

Zara Emberfire (Sorcerer Draconic Bloodline Lv 5 default).
Tests PATCH her subclass to "Wild Magic" + level to 6.

Tests:
  - Bonus mode: SP 5 → 3, d4 in 1..4, broadcast.
  - Penalty mode: signed value is negative.
  - Out of SP (1) → 409 out_of_uses.
  - Wrong subclass (Draconic) → 409.
  - Level gate at Lv 5 → 409.
  - Bad mode → 400.
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


def _bl_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "bend-luck"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _set_sp(gm_client, char_id, current):
    """Use the resource endpoint to flip sorcery-points current."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/resource",
        json={"key": "sorcery-points", "set": current},
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def zara_wild_magic_lv6(gm_client, roster):
    """PATCH Zara's subclass to 'Wild Magic' + level to 6 and
    seed her in a battle so the reaction chip mark succeeds."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 6},
        class_slug="sorcerer",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_bl_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 36, "hp_max": 36,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Ensure full SP (5).
    await _set_sp(gm_client, zara["id"], 5)
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )
        await _set_sp(gm_client, zara["id"], 5)


async def test_use_bend_luck_bonus(
    gm_client, gm_ws, zara_wild_magic_lv6,
):
    """Bonus mode → SP 5 → 3, d4 in 1..4, signed > 0."""
    zara = zara_wild_magic_lv6
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
        json={
            "character_id": zara["id"],
            "mode": "bonus",
            "target_name": "Bandit Alpha",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "bonus"
    assert 1 <= data["d4"] <= 4
    assert data["signed"] > 0
    assert data["sp_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _bl_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_use_bend_luck_penalty(
    gm_client, zara_wild_magic_lv6,
):
    """Penalty mode → signed value negative."""
    zara = zara_wild_magic_lv6
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
        json={
            "character_id": zara["id"],
            "mode": "penalty",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "penalty"
    assert data["signed"] < 0
    assert data["signed"] == -data["d4"]


async def test_use_bend_luck_out_of_sp(
    gm_client, zara_wild_magic_lv6,
):
    """SP at 1 → 409 out_of_uses."""
    zara = zara_wild_magic_lv6
    await _set_sp(gm_client, zara["id"], 1)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
        json={
            "character_id": zara["id"],
            "mode": "bonus",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_bend_luck_wrong_subclass(
    gm_client, roster,
):
    """Default Draconic Bloodline Zara → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
        json={
            "character_id": zara["id"],
            "mode": "bonus",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bend_luck_level_gate(
    gm_client, roster,
):
    """Wild Magic Zara at Lv 5 (not 6+) → 409. Briefly PATCH
    subclass without bumping level."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic"},
        class_slug="sorcerer",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
            json={
                "character_id": zara["id"],
                "mode": "bonus",
                "override": True,
            },
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_bend_luck_bad_mode(
    gm_client, zara_wild_magic_lv6,
):
    """mode = 'sideways' → 400."""
    zara = zara_wild_magic_lv6
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bend_luck",
        json={
            "character_id": zara["id"],
            "mode": "sideways",
            "override": True,
        },
    )
    assert r.status_code == 400, r.text
