"""v2.405.3 — /cast_geas endpoint + duration-scaling substrate, fourth
consumer (and the first NEW endpoint built on the substrate from the
start). RAW PHB p.244: L5 Enchantment, 60 ft, NOT concentration. On a
failed WIS save the target is charmed + compelled to follow a command.
Duration scales with slot level via `_SPELL_DURATION_MAP["geas"]`:

  - L5-L6 → 30 days  → marker "30d"
  - L7-L8 → 1 year   → marker "1y"
  - L9    → until dispelled → marker "permanent"

These are calendar durations, not combat rounds, so the substrate
returns marker strings the endpoint surfaces as `duration_label`.

Geas isn't on any demo PC's native spell list (Bard/Cleric/Druid/
Paladin/Wizard). Thalindra Moonwhisper (Wizard Lv 7) gets it for these
tests: the fixture snapshots her spells + wizard slot table, arms her
with Geas + an L5-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L5 → "30d", L7 → "1y", L9 → "permanent"
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
async def thalindra_geas(gm_client, roster):
    """Thalindra armed with Geas on her spell list + an L5-L9 wizard
    slot table so every duration tier is reachable. Snapshots +
    restores her spells + wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_geas = any(
        (s.get("_slug") == "geas")
        or (str(s.get("name", "")).lower() == "geas")
        for s in spells
    )
    if not has_geas:
        spells.append({
            "name": "Geas",
            "_slug": "geas",
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
        f"/api/campaign/{CAMPAIGN_ID}/cast_geas",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_geas_l5_routes_30d(gm_client, thalindra_geas):
    """L5 → "30d" marker; response `duration_label == "30d"`, not
    concentration. Base tier."""
    resp = await _cast(gm_client, thalindra_geas, slot_level=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_label"] == "30d", data
    assert data["range_ft"] == 60, data
    assert data["concentration"] is False, data


async def test_geas_l7_routes_1y(gm_client, thalindra_geas):
    """L7 → "1y" marker; `duration_label == "1y"`. Middle tier."""
    resp = await _cast(gm_client, thalindra_geas, slot_level=7)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "1y", data


async def test_geas_l9_routes_permanent(gm_client, thalindra_geas):
    """L9 → "permanent" marker (until dispelled); `duration_label ==
    "permanent"`. Reuses the v2.405.2 marker path."""
    resp = await _cast(gm_client, thalindra_geas, slot_level=9)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "permanent", data


async def test_geas_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_geas",
        json={"class_slug": "wizard", "slot_level": 5},
    )
    assert resp.status_code == 400, resp.text


async def test_geas_low_slot_400(gm_client, thalindra_geas):
    """slot_level=4 → 400 (Geas is L5)."""
    resp = await _cast(gm_client, thalindra_geas, slot_level=4)
    assert resp.status_code == 400, resp.text


async def test_geas_wrong_class_409(gm_client, thalindra_geas):
    """class_slug=barbarian (not a Geas class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_geas",
        json={
            "character_id": thalindra_geas["id"],
            "class_slug": "barbarian",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_geas_spell_not_known_409(gm_client, roster):
    """A Wizard without Geas on her list → 409 spell_not_known. Uses
    Thalindra WITHOUT the geas-arming fixture (native list lacks Geas).
    The spell-list check fires before the slot lookup, so no slot
    patching is needed (and none is done, to avoid leaking state)."""
    thal = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_geas",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
