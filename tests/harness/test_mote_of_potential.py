"""v2.99.326 — Creation College Bard: Mote of Potential (F.1 batch, Lv 3+, TCE).

F.1 Bard subclass batch ship #8 — CLOSES the F.1 Bard batch
(8/8 PHB+XGE+TCE subclasses with first non-spell-only
features wired). RAW TCE p.31: when a creature uses a BI die
from you, the Mote attaches + triggers an effect by mode:
- check: re-roll BI die, add to check.
- attack: BI die in force damage to nearby creature.
- save: temp HP = BI roll + CHA mod.

v1 announce-only — Mote roll + effect application GM-tracked.
No chip — passive rider on existing BI use.

Lyra Lv 6 CHA 17 mod 3 → die 1d8.

Tests:
  - Lv 3+ happy default check → 1d8 + CHA mod 3.
  - mode "attack" passthrough.
  - mode "save" passthrough.
  - Wrong subclass → 409.
  - Creation Lv 2 → 409.
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


def _mp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mote-of-potential"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_creation(gm_client, roster):
    """PATCH Lyra to College of Creation."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Creation"},
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


async def test_use_mp_happy_lv6_check(
    gm_client, gm_ws, lyra_creation,
):
    """Lv 6 Creation default check → 1d8 + CHA mod 3."""
    lyra = lyra_creation
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "check"
    assert data["die_size"] == 8
    assert data["die_expression"] == "1d8"
    assert data["cha_mod"] == 3
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _mp_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_mp_mode_attack(
    gm_client, lyra_creation,
):
    """mode='attack' passes through."""
    lyra = lyra_creation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "attack"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "attack"


async def test_use_mp_mode_save(
    gm_client, lyra_creation,
):
    """mode='save' passes through."""
    lyra = lyra_creation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "save"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "save"


async def _seed_lyra_plus_bandit(gm_client, lyra, bandit_cid):
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_mp_l_{lyra['id']}", "char_id": lyra["id"],
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


async def test_mp_attack_mode_applies_force_damage(
    gm_client, lyra_creation,
):
    """v2.670.0 — Phase 8: attack mode now rolls + applies 1d{die} force
    damage to the target via `_apply_damage_to_combatant` (was announce-
    only). Lv 6 Lyra → 1d8."""
    lyra = lyra_creation
    bandit_cid = "tok_mp_atk_bandit"
    await _seed_lyra_plus_bandit(gm_client, lyra, bandit_cid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "attack",
              "target_combatant_id": bandit_cid},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "attack"
    dr = data.get("die_rolled")
    da = data.get("damage_applied")
    assert dr is not None and 1 <= dr <= 8, f"1d8 should roll 1..8; got {dr}"
    # force damage vs a vanilla bandit applies fully; accept halving
    # defensively but it always lands ≥ 1 (min 1d8 = 1).
    assert da is not None and da > 0
    assert da in (dr, dr // 2), f"applied should be rolled or halved; got {dr}/{da}"


async def test_mp_save_mode_grants_temp_hp(
    gm_client, lyra_creation,
):
    """v2.670.0 — Phase 8: save mode now grants 1d{die} + CHA-mod temp HP to
    the target via `_grant_temp_hp` (was announce-only). Lv 6 Lyra CHA 17 →
    1d8 + 3, granted to a fresh NPC (no existing temp pool → applied full)."""
    lyra = lyra_creation
    bandit_cid = "tok_mp_save_bandit"
    await _seed_lyra_plus_bandit(gm_client, lyra, bandit_cid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "save",
              "target_combatant_id": bandit_cid},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "save"
    dr = data.get("die_rolled")
    thp = data.get("temp_hp_granted")
    cha = data.get("cha_mod")
    assert dr is not None and 1 <= dr <= 8
    assert cha == 3
    # Fresh target (no temp HP) → granted == roll + CHA mod.
    assert thp == dr + cha, f"temp HP should be {dr}+{cha}; got {thp}"


async def test_use_mp_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mp_level_gate(
    gm_client, roster,
):
    """Creation Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Creation", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
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
