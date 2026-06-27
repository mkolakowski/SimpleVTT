"""v2.713.0 — /cast_daylight endpoint + auto-placed vision-and-light
`daylight` emitter. RAW PHB p.230: L3 Evocation, 60 ft, 1 hour (NOT
concentration), no save, 60-ft-radius sphere of bright light (+60 ft dim)
that dispels magical darkness of 3rd level or lower. Radius fixed.
Classes: Cleric, Druid, Ranger, Sorcerer.

Brother Tavik Stonebrow (Cleric) is armed with Daylight + an L3-L9 cleric
slot table (snapshot + restored on teardown).

Tests:
  - happy path: cast → 200, radius_ft 60, range 60, concentration False;
  - cast with `center` → a `daylight` emitter (non-concentration) at the point;
  - cast without `center` → no emitter;
  - error paths: missing character_id 400, slot < 3 400, wrong class 409,
    spell not known 409.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def _patch(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields)
    assert r.status_code == 200, r.text


async def _clear_emitters(gm_client):
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    for e in body.get("light_emitters") or []:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/light_emitter/{e['id']}")


@pytest_asyncio.fixture
async def tavik_daylight(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    sheet = await _sheet(gm_client, tavik["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("cleric") or {})
    spells = list(orig_spells)
    if not any((s.get("_slug") == "daylight")
               or (str(s.get("name", "")).lower() == "daylight")
               for s in spells):
        spells.append({"name": "Daylight", "_slug": "daylight",
                       "level": 3, "class": "cleric"})
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(1, 10)}
    await _patch(gm_client, tavik["id"], {
        "spells": spells, "spell_slots": {"cleric": slot_table}})
    yield tavik
    await _patch(gm_client, tavik["id"], {
        "spells": orig_spells, "spell_slots": {"cleric": orig_slots}})


async def _cast(gm_client, tavik, slot_level=3, center=None):
    body = {"character_id": tavik["id"], "class_slug": "cleric",
            "slot_level": slot_level, "override": True}
    if center is not None:
        body["center"] = center
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_daylight", json=body)


async def test_daylight_happy(gm_client, tavik_daylight):
    resp = await _cast(gm_client, tavik_daylight)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["ok"] is True
    assert d["radius_ft"] == 60
    assert d["range_ft"] == 60
    assert d["concentration"] is False


async def test_daylight_with_center_places_emitter(gm_client, tavik_daylight):
    await _clear_emitters(gm_client)
    resp = await _cast(gm_client, tavik_daylight, center={"x": 200.0, "y": 200.0})
    assert resp.status_code == 200, resp.text
    eid = resp.json().get("emitter_id")
    assert eid, resp.text
    try:
        tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
        em = next((e for e in (tk.get("light_emitters") or [])
                   if e["id"] == eid), None)
        assert em, tk.get("light_emitters")
        assert em["kind"] == "daylight"
        assert em["radius_ft"] == 60
        assert em["x"] == 200.0 and em["y"] == 200.0
        assert em.get("concentration") is False
    finally:
        await _clear_emitters(gm_client)


async def test_daylight_no_center_no_emitter(gm_client, tavik_daylight):
    await _clear_emitters(gm_client)
    resp = await _cast(gm_client, tavik_daylight)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("emitter_id") is None
    tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    assert not (tk.get("light_emitters") or [])


async def test_daylight_missing_character_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_daylight",
        json={"class_slug": "cleric", "slot_level": 3})
    assert resp.status_code == 400, resp.text


async def test_daylight_low_slot_400(gm_client, tavik_daylight):
    resp = await _cast(gm_client, tavik_daylight, slot_level=2)
    assert resp.status_code == 400, resp.text


async def test_daylight_wrong_class_409(gm_client, tavik_daylight):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_daylight",
        json={"character_id": tavik_daylight["id"], "class_slug": "wizard",
              "slot_level": 3, "override": True})
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_daylight_spell_not_known_409(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_daylight",
        json={"character_id": tavik["id"], "class_slug": "cleric",
              "slot_level": 3, "override": True})
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
