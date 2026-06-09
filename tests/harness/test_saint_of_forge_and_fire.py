"""v2.99.299 → v2.158.2 — Forge Domain Cleric: Saint of Forge and Fire (Lv 17).

v2.99.299 shipped announce-only. v2.158.2 (Phase 8 second commit
of the [full-feature-automation](../../docs/plans/full-feature-automation.md)
plan; sibling of v2.158.0 Avatar of Battle) wires the endpoint
to install a permanent `saint-of-forge-and-fire` buff carrying
both `effects.immunity_to=["fire"]` (read by `_immunity_zero`)
and `effects.resistance_to=["nonmagical-bludgeoning",
"nonmagical-piercing","nonmagical-slashing"]` (read by the
v2.158.1-upgraded F6-aware `_resistance_halve`).

RAW XGE p.18: immunity to fire damage; while wearing heavy
armor, resistance to bludgeoning, piercing, slashing from
nonmagical attacks. v1 simplification: BPS halving installs
unconditionally pending a PC-armor-detection helper (Lv 17
Forge canonically wears heavy armor).

Tests:
  - Lv 17 happy → fire_immunity True, BPS resistance True,
    buff_installed True, broadcast.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Installed buff carries `effects.immunity_to` with "fire" +
    `effects.resistance_to` with the three nonmagical-X entries.
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


def _sff_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "saint-of-forge-and-fire"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """v2.158.2 — `_install_buff` requires an active battle. Seed a
    minimal one with Tavik so the endpoint can lay down the buff.
    """
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_sff_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def tavik_forge_lv17(gm_client, roster):
    """PATCH Tavik to Forge Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Forge Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_sff_happy_lv17(
    gm_client, gm_ws, tavik_forge_lv17,
):
    """Lv 17 Forge → fire immune + heavy-armor BPS resist, buff installed."""
    tavik = tavik_forge_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["fire_immunity"] is True
    assert data["heavy_armor_bps_resistance"] is True
    assert "bludgeoning" in data["resistance_types"]
    assert data["resistance_nonmagical_only"] is True
    assert data["cleric_level"] == 17
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _sff_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_sff_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sff_level_gate(
    gm_client, roster,
):
    """Forge Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Forge Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_sff_buff_payload_carries_fire_immunity_and_bps_resistance(
    gm_client, gm_ws, tavik_forge_lv17,
):
    """v2.158.2 — state contract (Phase 9): the installed
    `saint-of-forge-and-fire` buff carries BOTH
    `effects.immunity_to=["fire"]` (read by the PC `_immunity_zero`
    pipeline) AND `effects.resistance_to` with the three
    `nonmagical-X` entries (read by the v2.158.1-upgraded
    `_resistance_halve`). If either is missing the damage pipeline
    stops gating that part of the feature — this test pins both."""
    tavik = tavik_forge_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_saint_of_forge_and_fire",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    tavik_buffs = bu["data"]["buffs"]
    sff_buff = next(
        (b for b in tavik_buffs if b.get("key") == "saint-of-forge-and-fire"),
        None,
    )
    assert sff_buff is not None, (
        f"saint-of-forge-and-fire buff missing; got keys="
        f"{[b.get('key') for b in tavik_buffs]}"
    )
    effects = sff_buff.get("effects") or {}
    immunes = [(str(r) or "").strip().lower()
               for r in (effects.get("immunity_to") or [])]
    assert "fire" in immunes, (
        f"missing fire immunity; got immunity_to={immunes}"
    )
    resist = [(str(r) or "").strip().lower()
              for r in (effects.get("resistance_to") or [])]
    assert "nonmagical-bludgeoning" in resist, (
        f"missing nonmagical-bludgeoning; got resist={resist}"
    )
    assert "nonmagical-piercing" in resist, (
        f"missing nonmagical-piercing; got resist={resist}"
    )
    assert "nonmagical-slashing" in resist, (
        f"missing nonmagical-slashing; got resist={resist}"
    )
    # Permanent passive — no concentration, very long duration.
    assert sff_buff.get("concentration") in (False, None)
    assert int(sff_buff.get("duration_rounds") or 0) >= 1000
