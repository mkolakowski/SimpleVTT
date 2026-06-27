"""v2.99.325 — Spirits College Bard: Tales from Beyond (F.1 batch, Lv 3+, TCE).

F.1 Bard subclass batch ship #7. RAW TCE p.30: bonus action
to roll 1d6 on Spirit Tales table; action to apply the chosen
tale to a creature within 30 ft.

The 6 tales: Clever Animal / Renowned Duelist / Beloved Friends /
Brute / Tragic Romance / Traveler.

**v2.695.0 (Phase 8):** with a `target_combatant_id`, the four
mechanizable tales resolve server-side — 3/6 grant 2d6+bard_lv temp
HP; 4 (Brute) is a STR save → Prone + 2d10 force on a fail; 5 (Tragic
Romance) is a WIS save → Charmed. Tales 1/2 stay GM-narrated. Costs
bonus chip. `force_tale` body param (1-6) is a TEST_MODE escape hatch
(the apply tests use it for determinism — CI runs TEST_MODE=true).

Tests:
  - Lv 3+ random roll → tale_roll in [1,6], tale_name set.
  - force_tale=4 (Brute) → tale 4 with brute description.
  - force_tale=2 (Renowned Duelist) → tale 2.
  - Apply tale 3 → target gets 2d6+bard_lv temp HP (TEST_MODE).
  - Apply tale 4 → STR save resolved + 2d10 force on a fail (TEST_MODE).
  - Apply tale 5 → WIS save → Charmed on a fail (TEST_MODE).
  - No target → applied None (announce-only).
  - Wrong subclass → 409.
  - Spirits Lv 2 → 409.
"""
import asyncio
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_lyra_plus_bandit(gm_client, lyra, bandit_cid, hp=50, hp_max=50):
    """Seed Lyra + a templated bandit target for the apply tests."""
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_tb_l_{lyra['id']}", "char_id": lyra["id"],
             "name": lyra["name"], "initiative": 11,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_cid, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": hp, "hp_max": hp_max, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _tb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tales-from-beyond"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_spirits(gm_client, roster):
    """PATCH Lyra to College of Spirits."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Spirits"},
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


async def test_use_tb_happy_lv6(
    gm_client, gm_ws, lyra_spirits,
):
    """Lv 6 Spirits → tale_roll in [1,6], tale_name set."""
    lyra = lyra_spirits
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 1 <= data["tale_roll"] <= 6
    assert data["tale_name"]  # non-empty
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _tb_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_tb_force_tale_4_brute(
    gm_client, lyra_spirits,
):
    """force_tale=4 (Brute) → roll 4."""
    lyra = lyra_spirits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 4, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tale_roll"] == 4
    assert "Brute" in data["tale_name"]


async def test_use_tb_force_tale_2_duelist(
    gm_client, lyra_spirits,
):
    """force_tale=2 (Renowned Duelist) → roll 2."""
    lyra = lyra_spirits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 2, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tale_roll"] == 2
    assert "Duelist" in data["tale_name"]


async def test_tb_tale3_grants_temp_hp(
    gm_client, lyra_spirits,
):
    """v2.695.0 — Phase 8: tale 3 (Beloved Friends) grants 2d6+bard_lv temp
    HP to the target. Needs TEST_MODE for force_tale determinism — skip if
    off (the call returns a random tale locally)."""
    lyra = lyra_spirits
    await _seed_lyra_plus_bandit(gm_client, lyra, "tok_tb_t3")
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 3, "override": True,
              "target_combatant_id": "tok_tb_t3"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    if data["tale_roll"] != 3:
        pytest.skip("TEST_MODE off — force_tale ignored")
    ap = data["applied"]
    assert ap is not None and ap["kind"] == "temp_hp", data
    # Fresh target → full grant; amount = 2d6 + bard_lv (6) ∈ [8, 18].
    assert ap["temp_hp_granted"] == ap["temp_hp_amount"], ap
    assert 2 + 6 <= ap["temp_hp_amount"] <= 12 + 6


async def test_tb_tale4_brute_save_and_damage(
    gm_client, lyra_spirits,
):
    """v2.695.0 — Phase 8: tale 4 (Brute) rolls a STR save; on a fail the
    target takes 2d10 force + Prone. Skip if TEST_MODE off."""
    lyra = lyra_spirits
    await _seed_lyra_plus_bandit(gm_client, lyra, "tok_tb_t4")
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 4, "override": True,
              "target_combatant_id": "tok_tb_t4"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    if data["tale_roll"] != 4:
        pytest.skip("TEST_MODE off — force_tale ignored")
    ap = data["applied"]
    assert ap is not None and ap["kind"] == "brute", data
    fs = ap["feature_save"]
    assert fs is not None and fs["resolved"] is True, ap
    assert isinstance(fs["passed"], bool), fs
    if fs["passed"] is False:
        # 2d10 force applied + Prone installed.
        assert ap["force_damage_applied"] is not None
        assert 2 <= ap["force_damage_applied"] <= 20
        assert fs["condition_installed"] is True
        assert fs["condition_key"] == "prone"
    else:
        assert ap["force_damage_applied"] is None
        assert fs["condition_installed"] is False


async def test_tb_tale5_charm_save(
    gm_client, lyra_spirits,
):
    """v2.695.0 — Phase 8: tale 5 (Tragic Romance) rolls a WIS save → Charmed
    on a fail. Skip if TEST_MODE off."""
    lyra = lyra_spirits
    await _seed_lyra_plus_bandit(gm_client, lyra, "tok_tb_t5")
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 5, "override": True,
              "target_combatant_id": "tok_tb_t5"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    if data["tale_roll"] != 5:
        pytest.skip("TEST_MODE off — force_tale ignored")
    ap = data["applied"]
    assert ap is not None and ap["kind"] == "charm", data
    fs = ap["feature_save"]
    assert fs is not None and fs["resolved"] is True, ap
    assert fs["condition_installed"] == (not fs["passed"]), fs
    if fs["condition_installed"]:
        assert fs["condition_key"] == "charmed", fs


async def test_tb_no_target_announce_only(
    gm_client, lyra_spirits,
):
    """v2.695.0 — no target → applied stays None (announce-only)."""
    lyra = lyra_spirits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is None


async def test_use_tb_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tb_level_gate(
    gm_client, roster,
):
    """Spirits Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Spirits", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
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
