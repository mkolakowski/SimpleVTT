"""v2.99.224 — Thief Rogue features: Fast Hands + Supreme Sneak.

Phase E.4 of the v2.99.193 phased completion plan. RAW PHB
p.97:
  - Fast Hands (Lv 3): Cunning Action bonus can also be used
    for Sleight of Hand check / thieves' tools / Use an Object.
  - Supreme Sneak (Lv 9): advantage on Stealth check if you
    moved no more than half your speed this turn.

v1 ships:
  - /use_fast_hands: announce endpoint with mode param,
    marks bonus chip.
  - /use_supreme_sneak: installs `supreme-sneak-active` buff
    (+5 Stealth proxy for advantage), consumed by the v2.99.214
    /roll Stealth hook.

Thief's Reflexes (Lv 17) is filed — extra turn at -10 init is
too complex for v1 (init tracker doesn't support multi-entries
per combatant).

Pip Quickfingers (Thief Rogue Lv 7 default) is the demo
fixture; tests PATCH her Lv 7 → 9 for Supreme Sneak.

Tests:
  - Fast Hands sleight-of-hand mode happy path.
  - Fast Hands bad mode → 400.
  - Fast Hands wrong-class gate.
  - Supreme Sneak at Lv 9 happy path.
  - Supreme Sneak level gate (Lv 7).
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


def _fh_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fast-hands"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _ss_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "supreme-sneak"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_in_battle(gm_client, roster):
    """Seed Pip in an active battle so _install_buff can persist
    (needed for Supreme Sneak)."""
    pip = roster["Pip Quickfingers"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_thief_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 10, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    yield pip


async def test_use_fast_hands_sleight_of_hand(
    gm_client, gm_ws, pip_in_battle,
):
    """Pip Lv 7 → /use_fast_hands sleight-of-hand → 200 + broadcast."""
    pip = pip_in_battle
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fast_hands",
        json={
            "character_id": pip["id"],
            "mode": "sleight-of-hand",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "sleight-of-hand"
    await asyncio.sleep(0.3)
    feats = _fh_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_fast_hands_bad_mode(
    gm_client, roster,
):
    """Bad mode → 400."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fast_hands",
        json={
            "character_id": pip["id"],
            "mode": "pickpocket",
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_fast_hands_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fast_hands",
        json={
            "character_id": krieger["id"],
            "mode": "use-object",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_supreme_sneak_at_lv9(
    gm_client, gm_ws, pip_in_battle,
):
    """Pip PATCH'd to Lv 9 → /use_supreme_sneak → 200 + buff."""
    pip = pip_in_battle
    pre_level = 7
    await _patch_sheet(
        gm_client, pip["id"], {"level": 9},
        class_slug="rogue",
    )
    try:
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_sneak",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["stealth_bonus"] == 5
        assert data["buff_installed"] is True
        await asyncio.sleep(0.3)
        feats = _ss_broadcasts(gm_ws, pip["id"])
        assert feats
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": pre_level},
            class_slug="rogue",
        )


async def test_supreme_sneak_consumes_on_stealth_roll(
    gm_client, pip_in_battle,
):
    """v2.158.45 — Phase 2 read site for the v2.99.224
    `supreme-sneak-active` buff. Install the buff (Pip Lv 9), then roll
    a Stealth check → total gets +5 + breakdown mentions 'Supreme
    Sneak'. The buff is one-shot consumed: a second Stealth roll the
    same session gets no bonus."""
    pip = pip_in_battle
    await _patch_sheet(
        gm_client, pip["id"], {"level": 9}, class_slug="rogue")
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_sneak",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        await _seed_dice(gm_client, 42)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": "1d20",
                "character_id": pip["id"],
                "stat_key": "Stealth",
                "stat_ability": "DEX",
                "visibility": "public",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        breakdown = data.get("breakdown") or ""
        total = int(data.get("total") or 0)
        assert "Supreme Sneak" in breakdown, (
            f"expected breakdown to include 'Supreme Sneak'; "
            f"got {breakdown!r}"
        )
        # d20 (1-20) + 5 → 6-25.
        assert 6 <= total <= 25, (
            f"total should be d20 + 5; got {total}, "
            f"breakdown={breakdown!r}"
        )
        # One-shot consume: a second Stealth roll gets no bonus.
        r2 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": "1d20",
                "character_id": pip["id"],
                "stat_key": "Stealth",
                "stat_ability": "DEX",
                "visibility": "public",
            },
        )
        assert r2.status_code == 200, r2.text
        assert "Supreme Sneak" not in (r2.json().get("breakdown") or ""), (
            "buff should be consumed after the first Stealth roll"
        )
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": 7}, class_slug="rogue")


async def test_use_supreme_sneak_level_gate(
    gm_client, roster,
):
    """Control: Pip at Lv 7 → 409 wrong_subclass_or_level."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_supreme_sneak",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
