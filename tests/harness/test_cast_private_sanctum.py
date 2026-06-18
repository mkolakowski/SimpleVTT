"""v2.413.0 — /cast_private_sanctum endpoint, the fifth and final
consumer of the Phase 2 AoE-radius scaling substrate and the third
cube-edge shape (after Create or Destroy Water and Creation), closing
the arc. RAW PHB p.264: L4 Abjuration, 120 ft, 24 hours, no save, not
concentration. Secures a cube up to 100 ft on a side; the cube edge
scales with slot level via `_SPELL_AOE_MAP["private-sanctum"]` — the
largest increment in the substrate, +100 ft per slot above 4th:

  - L4 → 100 ft  (base)
  - L5 → 200 ft
  - L6 → 300 ft
  - L9 → 600 ft  (top in-table slot)

Surfaces `cube_ft`. Cast by Thalindra Moonwhisper (Wizard Lv 7): the
fixture snapshots her spells + wizard slot table, arms her with Private
Sanctum + an L4-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L4 → 100, L5 → 200, L6 → 300, L9 → 600 (cube_ft)
  - error paths: missing character_id → 400; slot_level < 4 → 400;
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
async def thalindra_private_sanctum(gm_client, roster):
    """Thalindra armed with Private Sanctum + an L4-L9 wizard slot table
    so every cube tier is reachable. Snapshots + restores her spells +
    wizard slots so other tests are untouched."""
    thal = roster[CASTER]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_ps = any(
        (s.get("_slug") == "private-sanctum")
        or (str(s.get("name", "")).lower() == "private sanctum")
        for s in spells
    )
    if not has_ps:
        spells.append({
            "name": "Private Sanctum",
            "_slug": "private-sanctum",
            "level": 4,
            "class": "wizard",
        })
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(4, 10)}
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
async def thalindra_no_private_sanctum(gm_client, roster):
    """Thalindra with Private Sanctum stripped from her spell list, so
    the spell_not_known path is reachable even if she knows it natively.
    Snapshots + restores her spells on teardown."""
    thal = roster[CASTER]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    stripped = [
        s for s in orig_spells
        if s.get("_slug") != "private-sanctum"
        and str(s.get("name", "")).lower() != "private sanctum"
    ]
    await _patch(gm_client, thal["id"], {"spells": stripped})
    yield thal
    await _patch(gm_client, thal["id"], {"spells": orig_spells})


async def _cast(gm_client, thal, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_private_sanctum",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_private_sanctum_l4_routes_100ft(gm_client, thalindra_private_sanctum):
    """L4 → 100-ft cube; not concentration, 120 ft range. Base tier."""
    resp = await _cast(gm_client, thalindra_private_sanctum, slot_level=4)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["cube_ft"] == 100, data
    assert data["range_ft"] == 120, data
    assert data["concentration"] is False, data


async def test_private_sanctum_l5_routes_200ft(gm_client, thalindra_private_sanctum):
    """L5 → 200-ft cube (+100 ft over base)."""
    resp = await _cast(gm_client, thalindra_private_sanctum, slot_level=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 200, resp.text


async def test_private_sanctum_l6_routes_300ft(gm_client, thalindra_private_sanctum):
    """L6 → 300-ft cube (100 + 2 × 100)."""
    resp = await _cast(gm_client, thalindra_private_sanctum, slot_level=6)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 300, resp.text


async def test_private_sanctum_l9_routes_600ft(gm_client, thalindra_private_sanctum):
    """L9 → 600-ft cube (100 + 5 × 100). Top in-table slot."""
    resp = await _cast(gm_client, thalindra_private_sanctum, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["cube_ft"] == 600, resp.text


async def test_private_sanctum_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_private_sanctum",
        json={"class_slug": "wizard", "slot_level": 4},
    )
    assert resp.status_code == 400, resp.text


async def test_private_sanctum_low_slot_400(gm_client, thalindra_private_sanctum):
    """slot_level=3 → 400 (Private Sanctum is L4)."""
    resp = await _cast(gm_client, thalindra_private_sanctum, slot_level=3)
    assert resp.status_code == 400, resp.text


async def test_private_sanctum_wrong_class_409(gm_client, thalindra_private_sanctum):
    """class_slug=cleric (not a Private Sanctum class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_private_sanctum",
        json={
            "character_id": thalindra_private_sanctum["id"],
            "class_slug": "cleric",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_private_sanctum_spell_not_known_409(gm_client, thalindra_no_private_sanctum):
    """A Wizard without Private Sanctum on her list → 409
    spell_not_known. The spell-list check fires before the slot lookup,
    so no slot patching is needed."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_private_sanctum",
        json={
            "character_id": thalindra_no_private_sanctum["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
