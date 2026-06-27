"""v2.99.308 — Mastermind Rogue: Master of Tactics (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #4. RAW XGE p.46: bonus action Help;
when helping an ally attack, target can be within 30 ft of
you (not 5 ft) if it can see/hear you.

**v2.701.0 (Phase 8):** RAW combat Help is target-specific, so with
`ally_combatant_id` + `target_combatant_id` the endpoint installs a
1-round buff on the ally carrying `attack_advantage_vs_target_combatant_id`
(+ `consume_on_attack`) — riding the True Strike / Vow of Enmity
advantage read. The ally's next /attack vs that target rolls with
advantage (2d20kh1), then the buff drops. Costs bonus chip.

Tests:
  - Lv 3+ happy (no ids) → help_action_economy bonus, range 30 ft,
    help_installed False (announce-only).
  - End-to-end: Pip helps Garrik vs a bandit → Garrik's attack rolls
    2d20kh1 (advantage from the installed buff).
  - Default Pip (Thief) → 409.
  - Mastermind Lv 2 → 409.
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


def _mt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "master-of-tactics"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_mastermind(gm_client, roster):
    """PATCH Pip to Mastermind subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Mastermind"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


async def test_use_mt_happy_lv7(
    gm_client, gm_ws, pip_mastermind,
):
    """Lv 7 Mastermind → bonus Help, 30 ft range."""
    pip = pip_mastermind
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["help_action_economy"] == "bonus"
    assert data["help_target_range_ft"] == 30
    assert data["rogue_level"] == 7
    assert data["help_installed"] is False  # no ally/target → announce-only
    await asyncio.sleep(0.3)
    feats = _mt_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_mt_grants_ally_advantage_vs_target(
    gm_client, pip_mastermind, roster,
):
    """v2.701.0 — Pip helps Garrik attack a bandit → the buff installs on
    Garrik keyed to the bandit; Garrik's next /attack vs that bandit rolls
    with advantage (2d20kh1). Proves the Help advantage rides the existing
    target-keyed read site."""
    pip = pip_mastermind
    garrik = roster["Garrik Ironside"]
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    pip_tok = f"tok_mt_pip_{pip['id']}"
    gar_tok = f"tok_mt_gar_{garrik['id']}"
    bandit_tok = "tok_mt_bandit"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
             "initiative": 14, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": gar_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Pip helps Garrik against the bandit.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
        json={"character_id": pip["id"], "override": True,
              "ally_combatant_id": gar_tok, "target_combatant_id": bandit_tok},
    )
    assert r.status_code == 200, r.text
    assert r.json()["help_installed"] is True, r.text
    # Garrik attacks the bandit → advantage (2d20kh1).
    ra = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": garrik["id"], "attack_index": 0,
              "target_combatant_id": bandit_tok, "override": True},
    )
    assert ra.status_code == 200, ra.text
    assert "2d20kh1" in (ra.json().get("attack_breakdown") or ""), ra.json()


async def test_use_mt_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mt_level_gate(
    gm_client, roster,
):
    """Mastermind Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Mastermind", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
            json={"character_id": pip["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )
