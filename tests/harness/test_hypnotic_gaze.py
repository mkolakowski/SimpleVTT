"""v2.99.330 — Enchantment Wizard: Hypnotic Gaze (G.1 batch, Lv 2+).

G.1 Wizard subclass batch ship #4. RAW PHB p.117: action,
target within 5 ft → WIS save DC 8 + prof + INT mod; on fail,
charmed + incapacitated + speed 0 until end of next turn.
Extendable as action on subsequent turns. Ends on damage,
caster moving >5 ft, or target losing sight/hearing. Once a
target succeeds, no re-use until long rest.

v1 announce-only — save + status install GM-tracked. Costs
action chip.

Thalindra Lv 7 prof 3 + INT 16 mod 3 → DC 14.

Tests:
  - Lv 7 happy → DC 14, WIS save, range 5 ft.
  - target_combatant_id passes through.
  - Wrong subclass → 409.
  - Enchantment Lv 1 → 409.
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


def _hg_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hypnotic-gaze"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_enchantment(gm_client, roster):
    """PATCH Thalindra to School of Enchantment."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Enchantment"},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_hg_happy_lv7(
    gm_client, gm_ws, thalindra_enchantment,
):
    """Lv 7 Enchantment (prof 3 + INT 16 mod 3) → DC 14."""
    thal = thalindra_enchantment
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hypnotic_gaze",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["save_ability"] == "WIS"
    assert data["range_ft"] == 5
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _hg_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_hg_with_target(
    gm_client, thalindra_enchantment,
):
    """target_combatant_id passes through."""
    thal = thalindra_enchantment
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hypnotic_gaze",
        json={"character_id": thal["id"], "target_combatant_id": "tok_test", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == "tok_test"


async def test_use_hg_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hypnotic_gaze",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_hg_level_gate(
    gm_client, roster,
):
    """Enchantment Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Enchantment", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hypnotic_gaze",
            json={"character_id": thal["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_hg_resolves_npc_save_installs_charmed(
    gm_client, gm_ws, thalindra_enchantment,
):
    """v2.99.413 — Phase 3.5: against an NPC target, Hypnotic Gaze
    auto-resolves the WIS save and installs Charmed on a fail.

    No resource counter (rest-gated), so call repeatedly with override;
    re-PUT the battle each iteration to reset the bandit. Loop until a
    fail lands (DC 14 vs a Bandit's +0 WIS).
    """
    thal = thalindra_enchantment
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    thal_tok = f"tok_hg_thal_{thal['id']}"
    bandit_tok = "tok_hg_bandit"

    def _battle():
        return {"combatants": [
            {"id": thal_tok, "char_id": thal["id"], "name": thal["name"],
             "initiative": 12, "hp_current": 37, "hp_max": 37, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": "Bandit",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True}

    installed = False
    for _ in range(40):
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle())
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_hypnotic_gaze",
            json={"character_id": thal["id"],
                  "target_combatant_id": bandit_tok, "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["save_resolved"] is True, data
        assert data["save_dc"] == 14
        if data["condition_installed"]:
            installed = True
            break
    assert installed, "no failed bandit WIS save in 40 tries"

    bu = await gm_ws.wait_for("battle_update")
    cb = next((c for c in (bu["data"].get("combatants") or [])
               if c.get("id") == bandit_tok), None)
    assert cb is not None
    ch = next((b for b in (cb.get("buffs") or [])
               if (b or {}).get("key") == "charmed"), None)
    assert ch is not None, cb.get("buffs")
    assert ch.get("name") == "Charmed (Hypnotic Gaze)"
    assert not ch.get("repeated_save_ability")  # sustained, no re-save
