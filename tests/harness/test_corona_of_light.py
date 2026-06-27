"""v2.99.293 — Light Domain Cleric: Corona of Light (H.1 deeper, Lv 17).

H.1 Lv 17 first ship — opens the H.1 Lv 17 batch. RAW PHB
p.61: action to activate 60 ft bright sunlight + 30 ft dim
beyond (90 ft total dim radius) for 1 min (or until dismissed
with another action). Enemies in the bright light have
disadvantage on saves vs your fire and radiant spells.

**v2.702.0 (Phase 8):** the endpoint installs a 1-min `corona-of-light`
buff; while active, the cleric's fire/radiant spell saves impose
**disadvantage** (2d20kl1) on enemy NPC savers, wired at the
single-target + AoE NPC save sites in `/cast_spell`. The 60-ft "in the
bright light" distance gate + non-caster spells + light emission stay
GM-narrated. Costs action chip. No per-rest gate (RAW at will).

Tavik PATCH'd to Light Domain Lv 17. (Tavik has Sacred Flame — a
radiant, DEX-save cantrip — for the end-to-end disadvantage test.)

Tests:
  - Lv 17 happy → bright 60, dim 90, 1 min, disadv fire+radiant,
    aura_installed True.
  - Disadvantage: corona active → Sacred Flame's NPC save rolls 2d20kl1
    (control without corona → 1d20).
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
"""
import asyncio
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _spell_index(gm_client, char_id, name):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    for i, sp in enumerate(sheet.get("spells") or []):
        nm = sp.get("name") if isinstance(sp, dict) else sp
        if str(nm).strip().lower() == name.strip().lower():
            return i
    return -1


async def _seed_tavik_plus_bandit(gm_client, tavik, bandit_cid):
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_col_t_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 12,
             "hp_current": 55, "hp_max": 55, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_cid, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 60, "hp_max": 60, "buffs": [],
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


def _col_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "corona-of-light"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_light_lv17(gm_client, roster):
    """PATCH Tavik to Light Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 17},
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


async def test_use_col_happy_lv17(
    gm_client, gm_ws, tavik_light_lv17,
):
    """Lv 17 Light → bright 60, dim 90, 1 min, disadv fire+radiant."""
    tavik = tavik_light_lv17
    # Seed a battle so `_install_buff` (the corona aura) lands.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_col_h_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 12,
             "hp_current": 55, "hp_max": 55, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bright_light_radius_ft"] == 60
    assert data["dim_light_radius_ft"] == 90
    assert data["duration_minutes"] == 1
    assert "fire" in data["save_disadvantage_types"]
    assert "radiant" in data["save_disadvantage_types"]
    assert data["cleric_level"] == 17
    assert data["aura_installed"] is True
    await asyncio.sleep(0.3)
    feats = _col_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_col_imposes_disadvantage_on_fire_radiant_save(
    gm_client, gm_ws, tavik_light_lv17,
):
    """v2.702.0 — with Corona active, the cleric's radiant spell (Sacred
    Flame, DEX save) makes the enemy NPC save at disadvantage (2d20kl1).
    Control without corona → a straight 1d20. Skips if Tavik has no Sacred
    Flame in his spell list."""
    tavik = tavik_light_lv17
    idx = await _spell_index(gm_client, tavik["id"], "Sacred Flame")
    if idx < 0:
        pytest.skip("Tavik has no Sacred Flame to cast")
    bandit_cid = "tok_col_bandit"
    await _seed_tavik_plus_bandit(gm_client, tavik, bandit_cid)

    def _save_rolls(since):
        return [
            m for m in gm_ws.buffered("roll")
            if "save" in ((m.get("data") or {}).get("note") or "").lower()
        ]

    # Control: no corona → straight d20 save.
    gm_ws.mark()
    rc = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": tavik["id"], "spell_index": idx,
              "target_combatant_id": bandit_cid},
    )
    assert rc.status_code == 200, rc.text
    await asyncio.sleep(0.3)
    ctrl = _save_rolls(None)
    assert ctrl, "expected a save roll broadcast for the control cast"
    assert not any("2d20kl1" in (m["data"].get("breakdown") or "")
                   for m in ctrl), ctrl[-1]["data"]

    # Activate Corona, then cast again → save at disadvantage.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
        json={"character_id": tavik["id"], "override": True},
    )
    gm_ws.mark()
    rd = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": tavik["id"], "spell_index": idx,
              "target_combatant_id": bandit_cid},
    )
    assert rd.status_code == 200, rd.text
    await asyncio.sleep(0.3)
    withc = _save_rolls(None)
    assert any("2d20kl1" in (m["data"].get("breakdown") or "")
               for m in withc), (
        "expected the NPC save to roll 2d20kl1 with Corona active; got "
        f"{[m['data'].get('breakdown') for m in withc]}"
    )


async def test_use_col_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain Lv 6) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_col_level_gate(
    gm_client, roster,
):
    """Light Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_corona_of_light",
            json={"character_id": tavik["id"], "override": True},
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
