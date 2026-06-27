"""v2.409.0 — /cast_fog_cloud endpoint + the Phase 2 AoE-radius scaling
substrate, first consumer. RAW PHB p.243: L1 Conjuration, 120 ft,
Concentration up to 1 hour, no save. Creates a 20-ft-radius sphere of
heavily obscuring fog. The radius scales with slot level via
`_SPELL_AOE_MAP["fog-cloud"]` — +20 ft per slot above 1st:

  - L1 → 20 ft   (base)
  - L2 → 40 ft
  - L5 → 100 ft
  - L9 → 180 ft  (top in-table slot)

Fog Cloud isn't on any demo PC's native spell list. Thalindra
Moonwhisper (Wizard Lv 7) gets it for these tests: the fixture
snapshots her spells + wizard slot table, arms her with Fog Cloud +
an L1-L9 slot table, and restores both on teardown.

Tests:
  - happy paths: L1 → 20, L2 → 40, L5 → 100, L9 → 180 (radius_ft)
  - error paths: missing character_id → 400; slot_level < 1 → 400;
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
async def thalindra_fog_cloud(gm_client, roster):
    """Thalindra armed with Fog Cloud + an L1-L9 wizard slot table so
    every radius tier is reachable. Snapshots + restores her spells +
    wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_fc = any(
        (s.get("_slug") == "fog-cloud")
        or (str(s.get("name", "")).lower() == "fog cloud")
        for s in spells
    )
    if not has_fc:
        spells.append({
            "name": "Fog Cloud",
            "_slug": "fog-cloud",
            "level": 1,
            "class": "wizard",
        })
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(1, 10)}
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
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_fog_cloud_l1_routes_20ft(gm_client, thalindra_fog_cloud):
    """L1 → 20-ft radius; concentration, 120 ft. Base tier."""
    resp = await _cast(gm_client, thalindra_fog_cloud, slot_level=1)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["radius_ft"] == 20, data
    assert data["range_ft"] == 120, data
    assert data["concentration"] is True, data


async def test_fog_cloud_l2_routes_40ft(gm_client, thalindra_fog_cloud):
    """L2 → 40-ft radius (+20 ft over base)."""
    resp = await _cast(gm_client, thalindra_fog_cloud, slot_level=2)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 40, resp.text


async def test_fog_cloud_l5_routes_100ft(gm_client, thalindra_fog_cloud):
    """L5 → 100-ft radius (20 + 4 × 20)."""
    resp = await _cast(gm_client, thalindra_fog_cloud, slot_level=5)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 100, resp.text


async def test_fog_cloud_l9_routes_180ft(gm_client, thalindra_fog_cloud):
    """L9 → 180-ft radius (20 + 8 × 20). Top in-table slot."""
    resp = await _cast(gm_client, thalindra_fog_cloud, slot_level=9)
    assert resp.status_code == 200, resp.text
    assert resp.json()["radius_ft"] == 180, resp.text


async def _clear_emitters(gm_client):
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    for e in body.get("light_emitters") or []:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/light_emitter/{e['id']}")


async def test_fog_cloud_with_center_places_fog_emitter(
    gm_client, thalindra_fog_cloud,
):
    """v2.711.0 — casting with a `center` auto-places a `fog` light emitter
    (Phase-3 vision-and-light) at that point with the scaled radius."""
    await _clear_emitters(gm_client)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={"character_id": thalindra_fog_cloud["id"], "class_slug": "wizard",
              "slot_level": 2, "override": True,
              "center": {"x": 300.0, "y": 250.0}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["radius_ft"] == 40, data
    assert data.get("emitter_id"), data
    try:
        tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
        ems = [e for e in (tk.get("light_emitters") or [])
               if e["id"] == data["emitter_id"]]
        assert ems, tk.get("light_emitters")
        em = ems[0]
        assert em["kind"] == "fog"
        assert em["radius_ft"] == 40
        assert em["x"] == 300.0 and em["y"] == 250.0
        assert em["caster_char_id"] == thalindra_fog_cloud["id"]
    finally:
        await _clear_emitters(gm_client)


async def test_fog_cloud_no_center_no_emitter(gm_client, thalindra_fog_cloud):
    """Casting without a `center` is backward-compatible — no emitter placed."""
    await _clear_emitters(gm_client)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={"character_id": thalindra_fog_cloud["id"], "class_slug": "wizard",
              "slot_level": 1, "override": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("emitter_id") is None, resp.text
    tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    assert not (tk.get("light_emitters") or []), tk.get("light_emitters")


async def test_fog_cloud_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={"class_slug": "wizard", "slot_level": 1},
    )
    assert resp.status_code == 400, resp.text


async def test_fog_cloud_low_slot_400(gm_client, thalindra_fog_cloud):
    """slot_level=0 → 400 (Fog Cloud is L1)."""
    resp = await _cast(gm_client, thalindra_fog_cloud, slot_level=0)
    assert resp.status_code == 400, resp.text


async def test_fog_cloud_wrong_class_409(gm_client, thalindra_fog_cloud):
    """class_slug=cleric (not a Fog Cloud class) → 409 wrong_class."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={
            "character_id": thalindra_fog_cloud["id"],
            "class_slug": "cleric",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_fog_cloud_spell_not_known_409(gm_client, roster):
    """A Wizard without Fog Cloud on her list → 409 spell_not_known.
    Uses Thalindra WITHOUT the arming fixture. The spell-list check
    fires before the slot lookup, so no slot patching is needed (and
    none is done, to avoid leaking state)."""
    thal = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fog_cloud",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
