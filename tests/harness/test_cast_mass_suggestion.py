"""v2.407.0 — /cast_mass_suggestion endpoint + duration-scaling
substrate, fifth consumer (second NEW endpoint built on the substrate,
after v2.406.0 /cast_geas). RAW PHB p.260: L6 Enchantment, 60 ft, NOT
concentration, up to 12 targets. On a failed WIS save each target
follows a suggested course of action. Duration scales with slot level
via `_SPELL_DURATION_MAP["mass-suggestion"]`:

  - L6 → 24 hours        → marker "24h"
  - L7 → 10 days         → marker "10d"
  - L8 → 30 days         → marker "30d"
  - L9 → a year and a day→ marker "1y1d"

Calendar-scale markers the endpoint surfaces as `duration_label`.

Mass Suggestion isn't on any demo PC's native spell list. Thalindra
Moonwhisper (Wizard Lv 7) gets it for these tests: the fixture
snapshots her spells + wizard slot table, arms her with Mass
Suggestion + an L6-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L6 → "24h", L7 → "10d", L8 → "30d", L9 → "1y1d"
  - error paths: missing character_id → 400; slot_level < 6 → 400;
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
async def thalindra_mass_suggestion(gm_client, roster):
    """Thalindra armed with Mass Suggestion + an L6-L9 wizard slot
    table so every duration tier is reachable. Snapshots + restores
    her spells + wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_ms = any(
        (s.get("_slug") == "mass-suggestion")
        or (str(s.get("name", "")).lower() == "mass suggestion")
        for s in spells
    )
    if not has_ms:
        spells.append({
            "name": "Mass Suggestion",
            "_slug": "mass-suggestion",
            "level": 6,
            "class": "wizard",
        })
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(6, 10)}
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
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_suggestion",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_mass_suggestion_l6_routes_24h(gm_client, thalindra_mass_suggestion):
    """L6 → "24h" marker; not concentration, 60 ft. Base tier."""
    resp = await _cast(gm_client, thalindra_mass_suggestion, slot_level=6)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_label"] == "24h", data
    assert data["range_ft"] == 60, data
    assert data["concentration"] is False, data


async def test_mass_suggestion_l7_routes_10d(gm_client, thalindra_mass_suggestion):
    """L7 → "10d" marker."""
    resp = await _cast(gm_client, thalindra_mass_suggestion, slot_level=7)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "10d", resp.text


async def test_mass_suggestion_l8_routes_30d(gm_client, thalindra_mass_suggestion):
    """L8 → "30d" marker."""
    resp = await _cast(gm_client, thalindra_mass_suggestion, slot_level=8)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "30d", resp.text


async def test_mass_suggestion_l9_routes_1y1d(gm_client, thalindra_mass_suggestion):
    """L9 → "1y1d" marker (a year and a day). Top tier."""
    resp = await _cast(gm_client, thalindra_mass_suggestion, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_label"] == "1y1d", resp.text


async def test_mass_suggestion_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_suggestion",
        json={"class_slug": "wizard", "slot_level": 6},
    )
    assert resp.status_code == 400, resp.text


async def test_mass_suggestion_low_slot_400(gm_client, thalindra_mass_suggestion):
    """slot_level=5 → 400 (Mass Suggestion is L6)."""
    resp = await _cast(gm_client, thalindra_mass_suggestion, slot_level=5)
    assert resp.status_code == 400, resp.text


async def test_mass_suggestion_wrong_class_409(gm_client, thalindra_mass_suggestion):
    """class_slug=cleric (not a Mass Suggestion class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_suggestion",
        json={
            "character_id": thalindra_mass_suggestion["id"],
            "class_slug": "cleric",
            "slot_level": 6,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_mass_suggestion_spell_not_known_409(gm_client, roster):
    """A Wizard without Mass Suggestion on her list → 409
    spell_not_known. Uses Thalindra WITHOUT the arming fixture. The
    spell-list check fires before the slot lookup, so no slot patching
    is needed (and none is done, to avoid leaking state)."""
    thal = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_suggestion",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
