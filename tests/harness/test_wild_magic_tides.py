"""v2.99.227 — Wild Magic Sorcerer: Tides of Chaos (Phase 1).

Phase E.6 Phase 1 of the v2.99.193 phased completion plan. RAW
PHB p.103: 1/long-rest advantage on one attack/check/save. See
docs/plans/wild-magic.md for the Phase 2-5 roadmap (Wild Magic
Surge auto-roll, Bend Luck reaction, Controlled Chaos, Spell
Bombardment).

v1 ships:
  - /use_tides_of_chaos: validates Wild Magic Sorcerer Lv 1+ +
    counter >= 1, decrements counter, installs buff, broadcasts.
  - /rest long-rest branch refills `sheet.tides_of_chaos_uses`
    to 1.

Zara Emberfire (Sorcerer Draconic Bloodline Lv 5 default) is
the demo fixture. Tests PATCH her subclass to "Wild Magic" +
counter to exercise.

Tests:
  - Tides of Chaos happy path (counter 1 → 0, buff installed,
    broadcast).
  - Tides of Chaos out_of_uses (counter 0) → 409.
  - Tides of Chaos wrong-class (Krieger Barbarian) → 409.
  - Tides of Chaos wrong-subclass (Zara default Draconic) → 409.
  - Long-rest refill (counter 0 → 1 via /rest).
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


def _toc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tides-of-chaos"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_wild_magic(gm_client, roster):
    """PATCH Zara's subclass to "Wild Magic" + counter to 1 + seed
    her in a battle so _install_buff persists. Restores on
    teardown."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "tides_of_chaos_uses": 1},
        class_slug="sorcerer",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wm_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "tides_of_chaos_uses": 0},
            class_slug="sorcerer",
        )


async def test_use_tides_of_chaos_happy_path(
    gm_client, gm_ws, zara_wild_magic,
):
    """Wild Magic Zara with counter 1 → 200, counter → 0,
    buff installed, broadcast."""
    zara = zara_wild_magic
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 0
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _toc_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_use_tides_of_chaos_out_of_uses(
    gm_client, zara_wild_magic,
):
    """Counter 0 → 409 out_of_uses."""
    zara = zara_wild_magic
    # Consume the one use first.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r1.status_code == 200, r1.text
    # Second invocation → 409.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "out_of_uses"


async def test_use_tides_of_chaos_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tides_of_chaos_wrong_subclass(
    gm_client, roster,
):
    """Zara default (Draconic Bloodline) → 409
    wrong_subclass_or_level."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


async def test_tides_of_chaos_grants_advantage_and_consumes(
    gm_client, zara_wild_magic,
):
    """v2.158.46 — Phase 2 read site for the v2.99.227
    `tides-of-chaos-active` buff. Install it (Wild Magic Zara), then roll
    a d20 ability check → the expression expands to 2d20kh1 (advantage) +
    breakdown mentions 'Tides of Chaos'. The buff is one-shot consumed: a
    second d20 roll rolls a straight 1d20 with no Tides mention."""
    zara = zara_wild_magic
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    await _seed_dice(gm_client, 7)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": zara["id"],
            "stat_key": "Arcana",
            "stat_ability": "INT",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("breakdown") or ""
    assert "Tides of Chaos" in breakdown, (
        f"expected breakdown to mention 'Tides of Chaos'; got {breakdown!r}"
    )
    assert "2d20" in breakdown, (
        f"expected advantage (2d20kh1) expansion; got {breakdown!r}"
    )
    # One-shot consume: a second d20 roll gets no advantage / no mention.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": zara["id"],
            "stat_key": "Arcana",
            "stat_ability": "INT",
            "visibility": "public",
        },
    )
    assert r2.status_code == 200, r2.text
    breakdown2 = r2.json().get("breakdown") or ""
    assert "Tides of Chaos" not in breakdown2, (
        f"buff should be consumed after the first d20 roll; got {breakdown2!r}"
    )
    assert "2d20" not in breakdown2, (
        f"second roll should be a straight 1d20; got {breakdown2!r}"
    )


async def test_tides_of_chaos_long_rest_refill(
    gm_client, zara_wild_magic,
):
    """After consuming the use, /rest long-rest restores
    sheet.tides_of_chaos_uses to 1."""
    zara = zara_wild_magic
    # Consume the use.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["uses_remaining"] == 0

    # Take a long rest.
    rest = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    assert rest.status_code == 200, rest.text

    # Confirm refill: a second /use_tides_of_chaos succeeds.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tides_of_chaos",
        json={"character_id": zara["id"]},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["uses_remaining"] == 0
