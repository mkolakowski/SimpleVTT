"""v2.99.354 — The Fathomless Warlock: Tentacle of the Deeps (G Warlock batch #6, Lv 1+, TCE).

Phase G Warlock patron subclass batch ship #6 — The Fathomless
opens.
RAW TCE p.70: bonus action, summon a 10-ft spectral tentacle
within 60 ft and make a melee spell attack vs a creature within
10 ft. On a hit: 1d8 cold (2d8 at Lv 10) + speed -10 ft for 1 min.
Summonable PB times per long rest.

v2.99.391 — Phase 1 of docs/plans/full-feature-automation.md: the
PB-per-long-rest budget is now server-tracked via the feature-use
registry (`sheet.tentacle_uses`, computed max = proficiency bonus):
each summon decrements, a depleted budget returns 409 `out_of_uses`,
and the /rest hook refills it. **v2.678.0 (Phase 8):** the melee spell attack is now resolved
server-side vs the target's AC (`_read_target_ac`) when a
`target_combatant_id` is supplied — nat 20 auto-crits (doubles the
dice), nat 1 auto-misses; on a hit the cold damage is applied via
`_apply_damage_to_combatant`. The speed reduction stays GM-narrated.
The cold damage is rolled + attack bonus computed server-side. Bonus
chip.

Magnus Hexbinder (Warlock, PATCHed to The Fathomless Lv 5) is the
demo fixture (1d8 cold below Lv 10; PB 3 → 3 uses).

Tests:
  - Lv 5 happy: cold in [1,8], reach 10, range 60, uses 3→2 (PB).
  - Apply: templated bandit target → attack rolled vs AC + cold applied.
  - Announce-only: no target → attack/damage fields stay None.
  - Exhausted budget (tentacle_uses=0) → 409 out_of_uses.
  - Long-rest refill: exhaust → /rest long → refills to PB (3).
  - Wrong subclass (default The Fiend) → 409.
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


def _td_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tentacle-of-the-deeps"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_fathomless(gm_client, roster):
    """PATCH Magnus to The Fathomless + seed the PB (3) use budget;
    restore to The Fiend."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Fathomless", "tentacle_uses": 3},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_td_happy_lv5(
    gm_client, gm_ws, magnus_fathomless,
):
    """Lv 5 Fathomless → 1d8 cold, reach 10, range 60, uses 3→2 (PB)."""
    magnus = magnus_fathomless
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "tentacle-of-the-deeps"
    assert data["damage_dice"] == "1d8"
    assert 1 <= data["cold_damage"] <= 8
    assert data["reach_ft"] == 10
    assert data["summon_range_ft"] == 60
    assert data["speed_reduction_ft"] == 10
    assert data["uses_max"] == 3  # proficiency bonus at Lv 5
    assert data["uses_remaining"] == 2
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _td_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["uses_remaining"] == 2


async def test_td_resolves_attack_and_applies_cold(
    gm_client, magnus_fathomless,
):
    """v2.678.0 — Phase 8: a templated NPC target now has the melee spell
    attack rolled vs its AC + the cold applied on a hit. Seed Magnus + a real
    bandit template, then assert the attack/damage fields are consistent with
    the rolled outcome (vanilla bandit → no cold resistance → exact)."""
    magnus = magnus_fathomless
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_td_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 12,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_td_bandit", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True,
              "target_combatant_id": "tok_td_bandit"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_ac"] is not None and data["target_ac"] >= 1
    assert 1 <= data["attack_nat"] <= 20
    assert data["attack_total"] == data["attack_nat"] + data["attack_bonus"]
    assert isinstance(data["hit"], bool)
    if data["hit"]:
        if data["is_crit"]:
            # crit rolls an extra dice_count d8 on top of the base roll.
            assert data["damage_applied"] >= data["cold_damage"], data
        else:
            assert data["damage_applied"] == data["cold_damage"], data
    else:
        assert data["damage_applied"] == 0, data


async def test_td_no_target_announce_only(
    gm_client, magnus_fathomless,
):
    """v2.678.0 — no target → backward-compatible announce-only."""
    magnus = magnus_fathomless
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["attack_nat"] is None
    assert data["attack_total"] is None
    assert data["hit"] is None
    assert data["damage_applied"] is None


async def test_use_td_out_of_uses(
    gm_client, roster,
):
    """Fathomless with an exhausted budget (0 uses) → 409 out_of_uses."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Fathomless", "tentacle_uses": 0},
        class_slug="warlock",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
            json={"character_id": magnus["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "out_of_uses"
        assert data.get("uses_remaining") == 0
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_td_long_rest_refill(
    gm_client, roster,
):
    """Exhausted Tentacle of the Deeps refills to PB (3) on a long rest
    — via the feature-use registry (computed max_fn)."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Fathomless", "tentacle_uses": 0},
        class_slug="warlock",
    )
    try:
        url = f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps"
        rest_url = (
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest"
        )
        r0 = await gm_client.post(url, json={
            "character_id": magnus["id"], "override": True})
        assert r0.status_code == 409, r0.text

        lr = await gm_client.post(rest_url, json={"type": "long"})
        assert lr.status_code == 200, lr.text
        r1 = await gm_client.post(url, json={
            "character_id": magnus["id"], "override": True})
        assert r1.status_code == 200, r1.text
        data = r1.json()
        assert data["uses_max"] == 3
        assert data["uses_remaining"] == 2  # refilled to 3, spent 1
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_td_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_td_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tentacle_of_the_deeps",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
