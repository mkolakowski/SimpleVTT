"""v2.99.317 — Spores Druid: Halo of Spores (E.4 batch, Lv 2+, TCE).

E.4 Druid ship #5 (Spores, TCE). RAW TCE p.36: reaction when
creature moves into or starts turn within 10 ft → necrotic
damage on failed CON save.

Damage die by druid level:
- Lv 2-5: 1d4
- Lv 6-9: 1d6
- Lv 10-13: 1d8
- Lv 14+: 1d10

**v2.676.0 (Phase 8):** the target's CON save is now rolled + the
necrotic damage applied server-side (was announce-only). RAW is
save-OR-NOTHING (no save-for-half): full `damage_rolled` on a fail,
ZERO on a success, via `_apply_damage_to_combatant`. Costs reaction
chip; no resolvable target → announce-only.

Mira Lv 5 → 1d4 + DC 14 (prof 3 + WIS 17 mod 3 + 8).

Tests:
  - Lv 5 happy → 1d4, DC 14, CON save, radius 10.
  - Apply: templated bandit target → save rolled + necrotic applied.
  - Announce-only: no target → save/damage fields stay None.
  - Lv 6 → 1d6.
  - Lv 14 → 1d10.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
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


def _hs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "halo-of-spores"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_spores(gm_client, roster):
    """PATCH Mira to Spores."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Spores"},
        class_slug="druid",
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_hs_happy_lv5(
    gm_client, gm_ws, mira_spores,
):
    """Lv 5 Spores → 1d4 necrotic, DC 14, CON save, radius 10."""
    mira = mira_spores
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "1d4"
    assert data["damage_type"] == "necrotic"
    assert data["save_ability"] == "CON"
    assert data["save_dc"] == 14
    assert data["aura_radius_ft"] == 10
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _hs_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_hs_applies_damage_to_target(
    gm_client, mira_spores,
):
    """v2.676.0 — Phase 8: a templated NPC target now has its CON save rolled
    + the necrotic applied server-side (save-OR-NOTHING). Seed Mira + a real
    bandit template, then assert the applied amount matches the outcome:
    full `damage_rolled` on a fail, 0 on a success (vanilla bandit → no
    necrotic resistance → exact)."""
    mira = mira_spores
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_hs_{mira['id']}", "char_id": mira["id"],
             "name": mira["name"], "initiative": 12,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_hs_bandit", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True,
              "target_combatant_id": "tok_hs_bandit"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_total"] is not None, data
    assert isinstance(data["save_passed"], bool), data
    assert data["damage_rolled"] is not None and 1 <= data["damage_rolled"] <= 4
    # save-or-nothing: 0 on a pass, full rolled on a fail.
    expected = 0 if data["save_passed"] else data["damage_rolled"]
    assert data["damage_applied"] == expected, data


async def test_hs_no_target_announce_only(
    gm_client, mira_spores,
):
    """v2.676.0 — no target → backward-compatible announce-only."""
    mira = mira_spores
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_total"] is None
    assert data["save_passed"] is None
    assert data["damage_applied"] is None


async def test_use_hs_lv6(
    gm_client, mira_spores,
):
    """Lv 6 → 1d6."""
    mira = mira_spores
    await _patch_sheet(
        gm_client, mira["id"], {"level": 6},
        class_slug="druid",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "1d6"


async def test_use_hs_lv14(
    gm_client, mira_spores,
):
    """Lv 14 → 1d10."""
    mira = mira_spores
    await _patch_sheet(
        gm_client, mira["id"], {"level": 14},
        class_slug="druid",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "1d10"


async def test_use_hs_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_hs_level_gate(
    gm_client, roster,
):
    """Spores Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Spores", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_halo_of_spores",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )
