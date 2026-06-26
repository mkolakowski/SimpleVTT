"""v2.99.321 — Glamour College Bard: Mantle of Inspiration (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #3. RAW XGE p.16: bonus action +
1 BI use → up to CHA-mod (min 1) allies within 60 ft each gain
5+bard_level temp HP + immediate reaction-move at full speed
without provoking OAs.

v2.671.0 — Phase 8: the temp HP half is now applied server-side
via ``_grant_temp_hp`` (the Mote of Potential save-mode / Inspiring
Smite substrate) to each named ally combatant, capped at CHA-mod.
The free reaction-move stays GM-narrated. Costs bonus chip; BI
decrement via existing flow. Backward-compatible: no
``target_combatant_ids`` → announce-only.

Lyra Lv 6 CHA 17 mod 3 → 3 allies × 11 temp HP each.

Tests:
  - Lv 6 happy → max_targets 3, temp_hp 11, max_range 60 ft.
  - apply → two named allies each granted 11 temp HP.
  - cap → 5 ids but only CHA-mod (3) buffed.
  - announce-only → no target ids → targets_buffed 0.
  - Wrong subclass → 409.
  - Glamour Lv 2 → 409.
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


def _mi_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mantle-of-inspiration"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_glamour(gm_client, roster):
    """PATCH Lyra to College of Glamour."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Glamour"},
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


async def test_use_mi_happy_lv6(
    gm_client, gm_ws, lyra_glamour,
):
    """Lv 6 Glamour, CHA 17 mod 3 → 3 allies × 11 temp HP."""
    lyra = lyra_glamour
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_targets"] == 3
    assert data["temp_hp_per_target"] == 11
    assert data["max_range_ft"] == 60
    assert data["free_move_no_oa"] is True
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _mi_broadcasts(gm_ws, lyra["id"])
    assert feats


async def _seed_lyra_plus_allies(gm_client, lyra, ally_cids):
    """Seed Lyra + N fresh ally combatants (no existing temp HP pool)."""
    combatants = [
        {"id": f"tok_mi_l_{lyra['id']}", "char_id": lyra["id"],
         "name": lyra["name"], "initiative": 11,
         "hp_current": 40, "hp_max": 40, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ]
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    for i, cid in enumerate(ally_cids):
        combatants.append({
            "id": cid, "char_id": None,
            "token_template_id": bandit["id"],
            "name": f"Ally {i}", "initiative": 8 - i,
            "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def test_mi_applies_temp_hp_to_allies(
    gm_client, lyra_glamour,
):
    """v2.671.0 — two named ally combatants each gain 5 + bard_level (= 11)
    temp HP, applied server-side via `_grant_temp_hp` (was announce-only)."""
    lyra = lyra_glamour
    ally_cids = ["tok_mi_a0", "tok_mi_a1"]
    await _seed_lyra_plus_allies(gm_client, lyra, ally_cids)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True,
              "target_combatant_ids": ally_cids},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["temp_hp_per_target"] == 11
    assert data["targets_buffed"] == 2
    applied = data["applied_targets"]
    assert len(applied) == 2
    # Fresh allies (no temp pool) → each granted the full 11.
    for row in applied:
        assert row["temp_hp_applied"] == 11, row


async def test_mi_caps_targets_at_cha_mod(
    gm_client, lyra_glamour,
):
    """v2.671.0 — more ids than CHA-mod (3) → only the first 3 are buffed."""
    lyra = lyra_glamour
    ally_cids = [
        "tok_mi_c0", "tok_mi_c1", "tok_mi_c2", "tok_mi_c3", "tok_mi_c4",
    ]
    await _seed_lyra_plus_allies(gm_client, lyra, ally_cids)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True,
              "target_combatant_ids": ally_cids},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_targets"] == 3
    assert data["targets_buffed"] == 3, data


async def test_mi_no_target_announce_only(
    gm_client, lyra_glamour,
):
    """v2.671.0 — no target ids → backward-compatible announce-only."""
    lyra = lyra_glamour
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["targets_buffed"] == 0
    assert data["applied_targets"] == []


async def test_use_mi_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mi_level_gate(
    gm_client, roster,
):
    """Glamour Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Glamour", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mantle_of_inspiration",
            json={"character_id": lyra["id"], "override": True},
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
