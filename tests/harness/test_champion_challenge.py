"""v2.99.384 — Oath of the Crown Paladin: Champion Challenge (G Paladin oath sweep, Lv 3+, SCAG).

Phase G Paladin oath sweep — Oath of the Crown.
RAW SCAG p.131 (Channel Divinity): as a bonus action, each chosen
creature within 30 ft makes a WIS save (DC 8 + PB + CHA mod); on a
failure it can't willingly move more than 30 ft away from you.

v2.99.393 — Phase 1: the Channel Divinity cost is now server-tracked
(spends from the shared `channel-divinity` pool; 409 `out_of_uses`
when depleted; refilled by /rest). The targeting + saves + movement
restriction stay GM-tracked pending the Phase 3 save resolver. The
save DC is computed server-side. Bonus chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oath of the Crown Lv
7) is the demo fixture.

Tests:
  - Lv 7 happy: WIS save DC >= 8, range 30, tether 30.
  - Wrong subclass (default Oath of Devotion) → 409.
  - Wrong class (Krieger barbarian) → 409.
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


def _cc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "champion-challenge"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_crown(gm_client, roster):
    """PATCH Caelan to Oath of the Crown + long-rest (refill Channel
    Divinity); restore to Devotion on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Crown"},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion"},
            class_slug="paladin",
        )


async def test_use_cc_happy_lv7(
    gm_client, gm_ws, caelan_crown,
):
    """Lv 7 Crown → WIS save DC, tether 30, Channel Divinity 1→0."""
    caelan = caelan_crown
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "champion-challenge"
    assert data["save"] == "wis"
    assert data["save_dc"] >= 8
    assert data["range_ft"] == 30
    assert data["tether_ft"] == 30
    assert data["cd_max"] == 1
    assert data["cd_remaining"] == 0
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _cc_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["cd_remaining"] == 0


async def test_use_cc_out_of_channel_divinity(
    gm_client, caelan_crown,
):
    """A second Champion Challenge with no Channel Divinity left → 409."""
    caelan = caelan_crown
    url = f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge"
    r1 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r1.status_code == 200, r1.text
    assert r1.json()["cd_remaining"] == 0
    r2 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r2.status_code == 409, r2.text
    assert r2.json().get("error") == "out_of_uses"


async def test_cc_resolves_npc_saves_installs_challenged(
    gm_client, gm_ws, caelan_crown,
):
    """v2.99.412 — Phase 3.4: with a target list, Champion Challenge
    resolves each creature's WIS save and installs a `challenged` marker
    on a fail (the >30-ft tether is GM-enforced).

    Multi-target → challenge several bandits in one call so a fail is
    near-certain; a small long-rest-refill loop backstops the rare
    all-pass. Asserts every target gets a resolved WIS save and the
    installed `challenged` buff has no repeated-save stamp.
    """
    caelan = caelan_crown
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    caelan_tok = f"tok_cc_{caelan['id']}"
    tok_ids = [f"tok_cc_bnd_{i}" for i in range(4)]

    def _battle():
        combs = [
            {"id": caelan_tok, "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ]
        for i, tid in enumerate(tok_ids):
            combs.append(
                {"id": tid, "char_id": None, "token_template_id": bandit["id"],
                 "name": f"Bandit {i}", "initiative": 8 - i,
                 "hp_current": 50, "hp_max": 50, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}})
        return {"combatants": combs, "turn_index": 0, "round": 1,
                "active": True}

    installed_on = None
    for _ in range(6):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle())
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
            json={"character_id": caelan["id"],
                  "target_combatant_ids": tok_ids, "override": True},
        )
        assert r.status_code == 200, r.text
        fs = r.json()["feature_saves"]
        assert len(fs) == len(tok_ids), fs
        for s in fs:
            assert s["resolved"] is True
            assert s["save_ability"] == "WIS"
        hit = next((s for s in fs if s["condition_installed"]), None)
        if hit:
            installed_on = hit["target_combatant_id"]
            break
    assert installed_on, "no failed bandit WIS save across 6 challenges"

    bu = await gm_ws.wait_for("battle_update")
    cb = next((c for c in (bu["data"].get("combatants") or [])
               if c.get("id") == installed_on), None)
    assert cb is not None
    ch = next((b for b in (cb.get("buffs") or [])
               if (b or {}).get("key") == "challenged"), None)
    assert ch is not None, cb.get("buffs")
    assert ch.get("name") == "Challenged (Champion Challenge)"
    assert not ch.get("repeated_save_ability")  # no repeated save


async def test_use_cc_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Oath of Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_cc_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_champion_challenge",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
