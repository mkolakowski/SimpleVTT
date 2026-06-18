"""v2.408.0 — /cast_modify_memory endpoint + duration-scaling
substrate, sixth consumer (third NEW endpoint built on the substrate,
after v2.406.0 /cast_geas and v2.407.0 /cast_mass_suggestion) and the
final Phase 1 spell. RAW PHB p.262: L5 Enchantment, 30 ft,
Concentration up to 1 minute, single target, WIS save. On a failed
save the caster reshapes one of the target's memories. The upcast
clause widens how far back the altered memory may reach; SimpleVTT
surfaces that as an escalating modification window scaling with slot
level via `_SPELL_DURATION_MAP["modify-memory"]`:

  - L5 → 10 minutes → marker "10min"
  - L6 → 1 hour     → marker "1h"
  - L7 → 24 hours   → marker "24h"
  - L8 → 7 days     → marker "7d"
  - L9 → permanent  → marker "permanent"

All-marker tiers the endpoint surfaces as `duration_label`.

Modify Memory isn't on any demo PC's native spell list. Thalindra
Moonwhisper (Wizard Lv 7) gets it for these tests: the fixture
snapshots her spells + wizard slot table, arms her with Modify
Memory + an L5-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L5 → "10min", L6 → "1h", L7 → "24h", L8 → "7d",
    L9 → "permanent"
  - error paths: missing character_id → 400; slot_level < 5 → 400;
    wrong class → 409; spell not known → 409
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
async def thalindra_modify_memory(gm_client, roster):
    """Thalindra armed with Modify Memory + an L5-L9 wizard slot table
    so every duration tier is reachable. Snapshots + restores her
    spells + wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_mm = any(
        (s.get("_slug") == "modify-memory")
        or (str(s.get("name", "")).lower() == "modify memory")
        for s in spells
    )
    if not has_mm:
        spells.append({
            "name": "Modify Memory",
            "_slug": "modify-memory",
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


async def _cast(gm_client, thal, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_modify_memory",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_modify_memory_l5_routes_10min(gm_client, thalindra_modify_memory):
    """L5 → "10min" marker; concentration, 30 ft. Base tier."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_label"] == "10min", data
    assert data["range_ft"] == 30, data
    assert data["concentration"] is True, data


async def test_modify_memory_l6_routes_1h(gm_client, thalindra_modify_memory):
    """L6 → "1h" marker."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=6)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "1h", resp.text


async def test_modify_memory_l7_routes_24h(gm_client, thalindra_modify_memory):
    """L7 → "24h" marker."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=7)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "24h", resp.text


async def test_modify_memory_l8_routes_7d(gm_client, thalindra_modify_memory):
    """L8 → "7d" marker."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=8)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "7d", resp.text


async def test_modify_memory_l9_routes_permanent(gm_client, thalindra_modify_memory):
    """L9 → "permanent" marker (any time in the past). Top tier."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "permanent", resp.text


async def test_modify_memory_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_modify_memory",
        json={"class_slug": "wizard", "slot_level": 5},
    )
    assert resp.status_code == 400, resp.text


async def test_modify_memory_low_slot_400(gm_client, thalindra_modify_memory):
    """slot_level=4 → 400 (Modify Memory is L5)."""
    resp = await _cast(gm_client, thalindra_modify_memory, slot_level=4)
    assert resp.status_code == 400, resp.text


async def test_modify_memory_wrong_class_409(gm_client, thalindra_modify_memory):
    """class_slug=cleric (not a Modify Memory class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_modify_memory",
        json={
            "character_id": thalindra_modify_memory["id"],
            "class_slug": "cleric",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_modify_memory_spell_not_known_409(gm_client, roster):
    """A Wizard without Modify Memory on her list → 409 spell_not_known.
    Uses Thalindra WITHOUT the arming fixture. The spell-list check
    fires before the slot lookup, so no slot patching is needed (and
    none is done, to avoid leaking state)."""
    thal = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_modify_memory",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
