"""v2.412.0 — /cast_creation endpoint + the Phase 2 AoE-radius scaling
substrate, fourth consumer and the second cube-edge shape (after Create
or Destroy Water). RAW PHB p.229: L5 Illusion, 30 ft, Special duration,
no save. Conjures a nonliving object no larger than a 5-ft cube. The
cube edge scales with slot level via `_SPELL_AOE_MAP["creation"]` —
+5 ft per slot above 5th:

  - L5 → 5 ft   (base)
  - L6 → 10 ft
  - L7 → 15 ft
  - L9 → 25 ft  (top in-table slot)

Surfaces `cube_ft`. Cast by Thalindra Moonwhisper (Wizard Lv 7): the
fixture snapshots her spells + wizard slot table, arms her with
Creation + an L5-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L5 → 5, L6 → 10, L7 → 15, L9 → 25 (cube_ft)
  - error paths: missing character_id → 400; slot_level < 5 → 400;
    wrong class → 409; spell not known → 409
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

CASTER = "Thalindra Moonwhisper"


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
async def thalindra_creation(gm_client, roster):
    """Thalindra armed with Creation + an L5-L9 wizard slot table so
    every cube tier is reachable. Snapshots + restores her spells +
    wizard slots so other tests are untouched."""
    thal = roster[CASTER]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_cr = any(
        (s.get("_slug") == "creation")
        or (str(s.get("name", "")).lower() == "creation")
        for s in spells
    )
    if not has_cr:
        spells.append({
            "name": "Creation",
            "_slug": "creation",
            "level": 5,
            "class": "wizard",
        })
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(5, 10)}
    await _patch(gm_client, thal["id"], {
        "spells": spells,
        "spell_slots": {"wizard": slot_table},
    })
    yield thal
    await _patch(gm_client, thal["id"], {
        "spells": orig_spells,
        "spell_slots": {"wizard": orig_slots},
    })


@pytest_asyncio.fixture
async def thalindra_no_creation(gm_client, roster):
    """Thalindra with Creation stripped from her spell list, so the
    spell_not_known path is reachable even if she knows it natively.
    Snapshots + restores her spells on teardown."""
    thal = roster[CASTER]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    stripped = [
        s for s in orig_spells
        if s.get("_slug") != "creation"
        and str(s.get("name", "")).lower() != "creation"
    ]
    await _patch(gm_client, thal["id"], {"spells": stripped})
    yield thal
    await _patch(gm_client, thal["id"], {"spells": orig_spells})


async def _cast(gm_client, thal, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_creation",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_creation_l5_routes_5ft(gm_client, thalindra_creation):
    """L5 → 5-ft cube; not concentration, 30 ft range. Base tier."""
    resp = await _cast(gm_client, thalindra_creation, slot_level=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["cube_ft"] == 5, data
    assert data["range_ft"] == 30, data
    assert data["concentration"] is False, data


async def test_creation_l6_routes_10ft(gm_client, thalindra_creation):
    """L6 → 10-ft cube (+5 ft over base)."""
    resp = await _cast(gm_client, thalindra_creation, slot_level=6)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 10, resp.text


async def test_creation_l7_routes_15ft(gm_client, thalindra_creation):
    """L7 → 15-ft cube (5 + 2 × 5)."""
    resp = await _cast(gm_client, thalindra_creation, slot_level=7)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 15, resp.text


async def test_creation_l9_routes_25ft(gm_client, thalindra_creation):
    """L9 → 25-ft cube (5 + 4 × 5). Top in-table slot."""
    resp = await _cast(gm_client, thalindra_creation, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 25, resp.text


async def test_creation_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_creation",
        json={"class_slug": "wizard", "slot_level": 5},
    )
    assert resp.status_code == 400, resp.text


async def test_creation_low_slot_400(gm_client, thalindra_creation):
    """slot_level=4 → 400 (Creation is L5)."""
    resp = await _cast(gm_client, thalindra_creation, slot_level=4)
    assert resp.status_code == 400, resp.text


async def test_creation_wrong_class_409(gm_client, thalindra_creation):
    """class_slug=cleric (not a Creation class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_creation",
        json={
            "character_id": thalindra_creation["id"],
            "class_slug": "cleric",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_creation_spell_not_known_409(gm_client, thalindra_no_creation):
    """A Wizard without Creation on her list → 409 spell_not_known. The
    spell-list check fires before the slot lookup, so no slot patching
    is needed."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_creation",
        json={
            "character_id": thalindra_no_creation["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
