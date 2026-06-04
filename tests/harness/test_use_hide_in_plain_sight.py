"""v2.99.214 — Hide in Plain Sight (Ranger Lv 10+).

Phase F.3 start of the v2.99.193 phased completion plan. RAW
PHB p.92: "Starting at 10th level, you can spend 1 minute
creating camouflage for yourself... You gain a +10 bonus to
Dexterity (Stealth) checks as long as you remain there without
moving or taking actions."

v1 ships:
  - `_pc_has_hide_in_plain_sight(sheet)` — Ranger Lv 10+ gate.
  - `_ranger_level_from_sheet(sheet)` — multiclass-aware level
    helper (mirror of `_rogue_level_from_sheet`).
  - `/use_hide_in_plain_sight` endpoint — installs
    `hide-in-plain-sight-active` buff with `stealth_bonus: 10`.
  - `/roll` Stealth consumer — when the buff is present, adds
    +10 to the total + removes the buff (one-shot consume).

v1 ignores the "must remain there without moving" condition;
the buff is consumed on the next Stealth roll regardless of
intervening actions. Filed.

Rowan Quickbow (Hunter Ranger Lv 7 default) is the demo fixture.

Tests:
  - Happy install: /use_hide_in_plain_sight at Lv 10 → buff
    installed + broadcast.
  - Happy consume: install buff + /roll Stealth → total +10 +
    buff removed.
  - Gate: Lv 7 default → 409 level_too_low.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _hips_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hide-in-plain-sight"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_lv10(gm_client, roster):
    """PATCH Rowan to Lv 10. Restore Lv 7 in teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 10},
        class_slug="ranger",
    )
    yield rowan
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 7},
        class_slug="ranger",
    )


async def test_use_hide_in_plain_sight_installs_buff(
    gm_client, gm_ws, rowan_lv10,
):
    """Rowan Lv 10 → /use_hide_in_plain_sight → buff installed +
    broadcast.
    """
    rowan = rowan_lv10
    rowan_tok = f"tok_hips_{rowan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": rowan_tok, "char_id": rowan["id"],
             "name": rowan["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hide_in_plain_sight",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stealth_bonus"] == 10
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _hips_broadcasts(gm_ws, rowan["id"])
    assert feats, (
        f"v2.99.214: expected feature_used(source=hide-in-plain-sight); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_hide_in_plain_sight_consumes_on_stealth_roll(
    gm_client, rowan_lv10,
):
    """Install buff, then roll Stealth → total = d20 + 10.
    """
    rowan = rowan_lv10
    # Seed a battle so _install_buff can persist on the combatant
    # + mirror the buff to the sheet.
    rowan_tok = f"tok_hips_{rowan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": rowan_tok, "char_id": rowan["id"],
             "name": rowan["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Install buff.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hide_in_plain_sight",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    # Roll Stealth with a seeded d20 (deterministic).
    await _seed_dice(gm_client, 42)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": rowan["id"],
            "stat_key": "Stealth",
            "stat_ability": "DEX",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("breakdown") or ""
    total = int(data.get("total") or 0)
    # The +10 should be added to the result. The breakdown should
    # mention "Hide in Plain Sight" via the post-result suffix.
    assert "Hide in Plain Sight" in breakdown, (
        f"v2.99.214: expected breakdown to include 'Hide in Plain "
        f"Sight'; got {breakdown!r}"
    )
    # Total is >= 11 (d20 1-20 + 10 = 11-30).
    assert 11 <= total <= 30, (
        f"v2.99.214: total should be d20 + 10; got {total}, "
        f"breakdown={breakdown!r}"
    )


async def test_use_hide_in_plain_sight_level_gate(
    gm_client, roster,
):
    """Control: Rowan at Lv 7 → 409 level_too_low."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hide_in_plain_sight",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 10
