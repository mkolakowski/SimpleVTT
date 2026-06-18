"""v2.411.0 — /cast_create_or_destroy_water endpoint + the Phase 2
AoE-radius scaling substrate, third consumer and the FIRST cube-edge
shape (after the two sphere-radius consumers Fog Cloud + Confusion).
RAW PHB p.229: L1 Transmutation, 30 ft, Instantaneous, no save. The
rain/destroy-fog mode fills a 30-ft cube. The cube edge scales with
slot level via `_SPELL_AOE_MAP["create-or-destroy-water"]` — +5 ft per
slot above 1st:

  - L1 → 30 ft  (base)
  - L2 → 35 ft
  - L5 → 50 ft
  - L9 → 70 ft  (top in-table slot)

Surfaces `cube_ft` rather than `radius_ft`. Cast by Brother Tavik
Stonebrow (Cleric Lv 8): the fixture snapshots his spells + cleric
slot table, arms him with Create or Destroy Water + an L1-L9 slot
table, and restores both on teardown.

Tests:
  - happy paths: L1 → 30, L2 → 35, L5 → 50, L9 → 70 (cube_ft)
  - error paths: missing character_id → 400; slot_level < 1 → 400;
    wrong class → 409; spell not known → 409
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

CASTER = "Brother Tavik Stonebrow"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def _patch(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def tavik_cdw(gm_client, roster):
    """Tavik armed with Create or Destroy Water + an L1-L9 cleric slot
    table so every cube tier is reachable. Snapshots + restores his
    spells + cleric slots so other tests are untouched."""
    tav = roster[CASTER]
    sheet = await _sheet(gm_client, tav["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("cleric") or {})

    spells = list(orig_spells)
    has_cdw = any(
        (s.get("_slug") == "create-or-destroy-water")
        or (str(s.get("name", "")).lower() == "create or destroy water")
        for s in spells
    )
    if not has_cdw:
        spells.append({
            "name": "Create or Destroy Water",
            "_slug": "create-or-destroy-water",
            "level": 1,
            "class": "cleric",
        })
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(1, 10)}
    await _patch(gm_client, tav["id"], {
        "spells": spells,
        "spell_slots": {"cleric": slot_table},
    })
    yield tav
    await _patch(gm_client, tav["id"], {
        "spells": orig_spells,
        "spell_slots": {"cleric": orig_slots},
    })


@pytest_asyncio.fixture
async def tavik_no_cdw(gm_client, roster):
    """Tavik with Create or Destroy Water stripped from his spell list,
    so the spell_not_known path is reachable even if he knows it
    natively in the demo. Snapshots + restores his spells on teardown."""
    tav = roster[CASTER]
    sheet = await _sheet(gm_client, tav["id"])
    orig_spells = list(sheet.get("spells") or [])
    stripped = [
        s for s in orig_spells
        if s.get("_slug") != "create-or-destroy-water"
        and str(s.get("name", "")).lower() != "create or destroy water"
    ]
    await _patch(gm_client, tav["id"], {"spells": stripped})
    yield tav
    await _patch(gm_client, tav["id"], {"spells": orig_spells})


async def _cast(gm_client, tav, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_create_or_destroy_water",
        json={
            "character_id": tav["id"],
            "class_slug": "cleric",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_cdw_l1_routes_30ft(gm_client, tavik_cdw):
    """L1 → 30-ft cube; not concentration, 30 ft range. Base tier."""
    resp = await _cast(gm_client, tavik_cdw, slot_level=1)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["cube_ft"] == 30, data
    assert data["range_ft"] == 30, data
    assert data["concentration"] is False, data


async def test_cdw_l2_routes_35ft(gm_client, tavik_cdw):
    """L2 → 35-ft cube (+5 ft over base)."""
    resp = await _cast(gm_client, tavik_cdw, slot_level=2)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 35, resp.text


async def test_cdw_l5_routes_50ft(gm_client, tavik_cdw):
    """L5 → 50-ft cube (30 + 4 × 5)."""
    resp = await _cast(gm_client, tavik_cdw, slot_level=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 50, resp.text


async def test_cdw_l9_routes_70ft(gm_client, tavik_cdw):
    """L9 → 70-ft cube (30 + 8 × 5). Top in-table slot."""
    resp = await _cast(gm_client, tavik_cdw, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 70, resp.text


async def test_cdw_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_create_or_destroy_water",
        json={"class_slug": "cleric", "slot_level": 1},
    )
    assert resp.status_code == 400, resp.text


async def test_cdw_low_slot_400(gm_client, tavik_cdw):
    """slot_level=0 → 400 (Create or Destroy Water is L1)."""
    resp = await _cast(gm_client, tavik_cdw, slot_level=0)
    assert resp.status_code == 400, resp.text


async def test_cdw_wrong_class_409(gm_client, tavik_cdw):
    """class_slug=wizard (not a Create/Destroy Water class) → 409
    wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_create_or_destroy_water",
        json={
            "character_id": tavik_cdw["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_cdw_spell_not_known_409(gm_client, tavik_no_cdw):
    """A Cleric without Create or Destroy Water on his list → 409
    spell_not_known. The spell-list check fires before the slot lookup,
    so no slot patching is needed."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_create_or_destroy_water",
        json={
            "character_id": tavik_no_cdw["id"],
            "class_slug": "cleric",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
