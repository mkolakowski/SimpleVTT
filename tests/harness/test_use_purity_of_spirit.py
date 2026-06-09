"""v2.99.154 → v2.158.10 — /use_purity_of_spirit endpoint tests.

Purity of Spirit is a Paladin Oath of Devotion Lv 15+ feature:
always under the effects of Protection from Evil and Good (PHB
p.87). v2.158.10 (Phase 8 step-out to the Lv-15 tier) wires
the endpoint to install a permanent `purity-of-spirit` buff
carrying the same `pfeag_*` effects payload the cast spell
uses. The two existing PFE&G read sites
(`_target_attackers_have_pfeag_disadvantage_against_type` +
`_pc_has_pfeag_against_type`) were extended to accept either
`key="purity-of-spirit"` or `key="protection-from-evil-and-
good"` so the class feature reuses the spell-buff engine
wholesale.

Sir Caelan Lightbringer is the Paladin fixture. Stock sheet is
Lv 6 Oath of Devotion — below the Lv 15 prerequisite — so the
harness PATCHes him to Lv 15 in the fixture and restores Lv 6
in teardown.

Tests:
  - happy path (Caelan at Lv 15 Devotion) → 200 + WS
    feature_used broadcast with `source: purity-of-spirit` +
    `protected_against` list of 6 creature types +
    `buff_installed == True`.
  - level gate (Caelan at stock Lv 6) → 409 missing_feature.
  - missing character_id → 400.
  - state contract: installed buff carries the four `pfeag_*`
    effect keys + permanence sanity.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_caelan_in_battle(gm_client, caelan):
    """v2.158.10 — `_install_buff` requires an active battle.
    Seed a minimal one with Caelan."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_pos_caelan_{caelan['id']}", caelan)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def caelan_at_lv_15(gm_client, roster):
    """PATCH Sir Caelan to Paladin Lv 15 (Purity of Spirit
    prereq). Restore Lv 6 in teardown.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 15},
    )
    yield caelan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 6},
    )


async def test_use_purity_of_spirit_happy_path(
    gm_client, gm_ws, caelan_at_lv_15,
):
    """Caelan at Lv 15 Devotion → 200 + audit broadcast with the
    6-creature protected_against list + buff_installed True.
    """
    caelan = caelan_at_lv_15
    await _seed_caelan_in_battle(gm_client, caelan)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["character_id"] == caelan["id"]
    protected = data.get("protected_against") or []
    assert "fiend" in protected
    assert "undead" in protected
    assert len(protected) == 6
    assert data["buff_installed"] is True
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "purity-of-spirit"
    assert bd.get("character_id") == caelan["id"]
    assert "fiend" in (bd.get("protected_against") or [])


async def test_pos_buff_payload_carries_pfeag_effects(
    gm_client, gm_ws, caelan_at_lv_15,
):
    """v2.158.10 — state contract (Phase 9): the installed
    `purity-of-spirit` buff carries the four `pfeag_*` effect
    keys with the right values (protected_types list, attackers
    disadvantage flag, charm/frighten/possess immunity flag,
    save advantage flag). The existing PFE&G engine read sites
    (`_target_attackers_have_pfeag_disadvantage_against_type` +
    `_pc_has_pfeag_against_type`) accept this key alongside the
    cast spell's key, so the same engine logic fires for the
    class-feature buff."""
    caelan = caelan_at_lv_15
    await _seed_caelan_in_battle(gm_client, caelan)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 200, resp.text
    bu = await gm_ws.wait_for("buff_update")
    caelan_buffs = bu["data"]["buffs"]
    pos_buff = next(
        (b for b in caelan_buffs if b.get("key") == "purity-of-spirit"),
        None,
    )
    assert pos_buff is not None, (
        f"purity-of-spirit buff missing; got keys="
        f"{[b.get('key') for b in caelan_buffs]}"
    )
    effects = pos_buff.get("effects") or {}
    protected = effects.get("pfeag_protected_types") or []
    assert "aberration" in protected
    assert "celestial" in protected
    assert "elemental" in protected
    assert "fey" in protected
    assert "fiend" in protected
    assert "undead" in protected
    assert effects.get("pfeag_attackers_have_disadvantage") is True
    assert effects.get("pfeag_immune_to_charm_frighten_possess") is True
    assert effects.get("pfeag_advantage_on_saves_vs_types") is True
    # Permanent passive — no concentration, very long duration.
    assert pos_buff.get("concentration") in (False, None)
    assert int(pos_buff.get("duration_rounds") or 0) >= 1000


async def test_use_purity_of_spirit_below_lv_15_409(gm_client, roster):
    """Caelan at stock Lv 6 → 409 missing_feature (level gate)."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_feature"
    assert data.get("feature") == "purity-of-spirit"


async def test_use_purity_of_spirit_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={},
    )
    assert resp.status_code == 400, resp.text
