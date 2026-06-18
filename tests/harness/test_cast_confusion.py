"""v2.410.0 — /cast_confusion endpoint + the Phase 2 AoE-radius scaling
substrate, second consumer (after v2.409.0 /cast_fog_cloud). RAW PHB
p.224: L4 Enchantment, 90 ft, Concentration up to 1 minute, WIS save.
Creatures in a 10-ft-radius sphere that fail the save are afflicted by
the confusion behavior table. The radius scales with slot level via
`_SPELL_AOE_MAP["confusion"]` — +5 ft per slot above 4th:

  - L4 → 10 ft  (base)
  - L5 → 15 ft
  - L6 → 20 ft
  - L9 → 35 ft  (top in-table slot)

Confusion isn't on any demo PC's native spell list. Thalindra
Moonwhisper (Wizard Lv 7) gets it for these tests: the fixture
snapshots her spells + wizard slot table, arms her with Confusion +
an L4-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L4 → 10, L5 → 15, L6 → 20, L9 → 35 (radius_ft)
  - error paths: missing character_id → 400; slot_level < 4 → 400;
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
async def thalindra_confusion(gm_client, roster):
    """Thalindra armed with Confusion + an L4-L9 wizard slot table so
    every radius tier is reachable. Snapshots + restores her spells +
    wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_cf = any(
        (s.get("_slug") == "confusion")
        or (str(s.get("name", "")).lower() == "confusion")
        for s in spells
    )
    if not has_cf:
        spells.append({
            "name": "Confusion",
            "_slug": "confusion",
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
async def thalindra_no_confusion(gm_client, roster):
    """Thalindra with Confusion stripped from her spell list (she knows
    it natively in the demo), so the spell_not_known path is reachable.
    Snapshots + restores her spells on teardown."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    stripped = [
        s for s in orig_spells
        if s.get("_slug") != "confusion"
        and str(s.get("name", "")).lower() != "confusion"
    ]
    await _patch(gm_client, thal["id"], {"spells": stripped})
    yield thal
    await _patch(gm_client, thal["id"], {"spells": orig_spells})


async def _cast(gm_client, thal, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_confusion",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_confusion_l4_routes_10ft(gm_client, thalindra_confusion):
    """L4 → 10-ft radius; concentration, 90 ft. Base tier."""
    resp = await _cast(gm_client, thalindra_confusion, slot_level=4)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["radius_ft"] == 10, data
    assert data["range_ft"] == 90, data
    assert data["concentration"] is True, data


async def test_confusion_l5_routes_15ft(gm_client, thalindra_confusion):
    """L5 → 15-ft radius (+5 ft over base)."""
    resp = await _cast(gm_client, thalindra_confusion, slot_level=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 15, resp.text


async def test_confusion_l6_routes_20ft(gm_client, thalindra_confusion):
    """L6 → 20-ft radius (10 + 2 × 5)."""
    resp = await _cast(gm_client, thalindra_confusion, slot_level=6)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 20, resp.text


async def test_confusion_l9_routes_35ft(gm_client, thalindra_confusion):
    """L9 → 35-ft radius (10 + 5 × 5). Top in-table slot."""
    resp = await _cast(gm_client, thalindra_confusion, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 35, resp.text


async def test_confusion_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_confusion",
        json={"class_slug": "wizard", "slot_level": 4},
    )
    assert resp.status_code == 400, resp.text


async def test_confusion_low_slot_400(gm_client, thalindra_confusion):
    """slot_level=3 → 400 (Confusion is L4)."""
    resp = await _cast(gm_client, thalindra_confusion, slot_level=3)
    assert resp.status_code == 400, resp.text


async def test_confusion_wrong_class_409(gm_client, thalindra_confusion):
    """class_slug=cleric (not a Confusion class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_confusion",
        json={
            "character_id": thalindra_confusion["id"],
            "class_slug": "cleric",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_confusion_spell_not_known_409(gm_client, thalindra_no_confusion):
    """A Wizard without Confusion on her list → 409 spell_not_known.
    Thalindra knows Confusion natively in the demo, so the
    `thalindra_no_confusion` fixture strips it (snapshot/restore). The
    spell-list check fires before the slot lookup, so no slot patching
    is needed."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_confusion",
        json={
            "character_id": thalindra_no_confusion["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
