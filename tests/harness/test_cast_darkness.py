"""v2.712.0 — /cast_darkness endpoint + auto-placed vision-and-light
`darkness` emitter. RAW PHB p.230: L2 Evocation, 60 ft, Concentration up to
10 min, no save, 15-ft-radius sphere of *magical* darkness (darkvision can't
pierce it; only Devil's Sight / truesight). Radius is fixed (no slot scaling).
Classes: Druid, Sorcerer, Warlock, Wizard.

Thalindra Moonwhisper (Wizard) is armed with Darkness + an L2-L9 slot table
(snapshot + restored on teardown).

Tests:
  - happy path: cast → 200, radius_ft 15, range 60, concentration;
  - cast with `center` → a `darkness` emitter at that point;
  - cast without `center` → no emitter (backward compat);
  - error paths: missing character_id 400, slot < 2 400, wrong class 409,
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
async def thalindra_darkness(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})
    spells = list(orig_spells)
    if not any((s.get("_slug") == "darkness")
               or (str(s.get("name", "")).lower() == "darkness")
               for s in spells):
        spells.append({"name": "Darkness", "_slug": "darkness",
                       "level": 2, "class": "wizard"})
    slot_table = {str(lv): {"total": 2, "used": 0} for lv in range(1, 10)}
    await _patch(gm_client, thal["id"], {
        "spells": spells, "spell_slots": {"wizard": slot_table}})
    yield thal
    await _patch(gm_client, thal["id"], {
        "spells": orig_spells, "spell_slots": {"wizard": orig_slots}})


async def _cast(gm_client, thal, slot_level=2, center=None):
    body = {"character_id": thal["id"], "class_slug": "wizard",
            "slot_level": slot_level, "override": True}
    if center is not None:
        body["center"] = center
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkness", json=body)


async def test_darkness_happy(gm_client, thalindra_darkness):
    resp = await _cast(gm_client, thalindra_darkness)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["ok"] is True
    assert d["radius_ft"] == 15
    assert d["range_ft"] == 60
    assert d["concentration"] is True


async def test_darkness_with_center_places_emitter(gm_client, thalindra_darkness):
    await _clear_emitters(gm_client)
    resp = await _cast(gm_client, thalindra_darkness,
                       center={"x": 410.0, "y": 360.0})
    assert resp.status_code == 200, resp.text
    eid = resp.json().get("emitter_id")
    assert eid, resp.text
    try:
        tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
        em = next((e for e in (tk.get("light_emitters") or [])
                   if e["id"] == eid), None)
        assert em, tk.get("light_emitters")
        assert em["kind"] == "darkness"
        assert em["radius_ft"] == 15
        assert em["x"] == 410.0 and em["y"] == 360.0
        assert em["caster_char_id"] == thalindra_darkness["id"]
    finally:
        await _clear_emitters(gm_client)


async def test_darkness_no_center_no_emitter(gm_client, thalindra_darkness):
    await _clear_emitters(gm_client)
    resp = await _cast(gm_client, thalindra_darkness)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("emitter_id") is None
    tk = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    assert not (tk.get("light_emitters") or [])


async def test_darkness_missing_character_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkness",
        json={"class_slug": "wizard", "slot_level": 2})
    assert resp.status_code == 400, resp.text


async def test_darkness_low_slot_400(gm_client, thalindra_darkness):
    resp = await _cast(gm_client, thalindra_darkness, slot_level=1)
    assert resp.status_code == 400, resp.text


async def test_darkness_wrong_class_409(gm_client, thalindra_darkness):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkness",
        json={"character_id": thalindra_darkness["id"], "class_slug": "cleric",
              "slot_level": 2, "override": True})
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "wrong_class"


async def test_darkness_spell_not_known_409(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_darkness",
        json={"character_id": thal["id"], "class_slug": "wizard",
              "slot_level": 2, "override": True})
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "spell_not_known"
