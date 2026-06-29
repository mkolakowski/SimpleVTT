"""v2.747.0 — summon-picker options endpoint.

`GET /api/campaign/{cid}/summon-options?spell=&count=` lists the catalog
creatures a player may pick for a count-based conjure spell, filtered by the
spell's creature type + the count↔CR tier — the same gate
`_conjure_catalog_summon_template` enforces on the cast, so every option is
guaranteed castable. Feeds the sheet-side summon picker (behavior #1 of the
Summon cast-flow arc).
"""
from .conftest import CAMPAIGN_ID

_URL = f"/api/campaign/{CAMPAIGN_ID}/summon-options"


async def test_conjure_animals_cr_quarter_tier(gm_client):
    r = await gm_client.get(_URL, params={"spell": "conjure-animals", "count": 8})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "beast"
    assert body["max_cr"] == 0.25
    opts = body["options"]
    assert opts, "expected beast options at CR 1/4"
    for o in opts:
        assert {"slug", "name", "cr", "hp", "ac"} <= o.keys()
        assert o["cr"] <= 0.25
    slugs = {o["slug"] for o in opts}
    # A CR-1 beast must NOT appear in the 8-creature (CR 1/4) tier.
    assert "brown-bear" not in slugs


async def test_conjure_animals_count_two_raises_cr_cap(gm_client):
    """count=2 → CR 1 tier, which now includes the RAW CR-1 beasts."""
    r = await gm_client.get(_URL, params={"spell": "conjure-animals", "count": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_cr"] == 1.0
    slugs = {o["slug"] for o in body["options"]}
    assert "brown-bear" in slugs  # CR 1, now allowed
    # Sorted CR desc → the first option is at the cap.
    assert body["options"][0]["cr"] == 1.0


async def test_woodland_beings_is_fey(gm_client):
    r = await gm_client.get(
        _URL, params={"spell": "conjure-woodland-beings", "count": 4})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "fey"
    assert all(o["cr"] <= 0.5 for o in body["options"])


async def test_conjure_elemental_single_slot_scaled(gm_client):
    """v2.749.0 — single-summon conjures: one creature, CR scales with the
    slot. Conjure Elemental @5th → elementals CR ≤ 5; @7th raises the cap."""
    r5 = await gm_client.get(
        _URL, params={"spell": "conjure-elemental", "slot_level": 5})
    assert r5.status_code == 200, r5.text
    b5 = r5.json()
    assert b5["mode"] == "single"
    assert b5["type"] == "elemental"
    assert b5["max_cr"] == 5
    assert b5["options"], "expected elementals at CR ≤ 5"
    assert all(o["cr"] <= 5 for o in b5["options"])
    slugs5 = {o["slug"] for o in b5["options"]}
    assert "fire-elemental" in slugs5  # CR 5

    r7 = await gm_client.get(
        _URL, params={"spell": "conjure-elemental", "slot_level": 7})
    assert r7.json()["max_cr"] == 7
    # The higher cap admits at least as many creatures.
    assert len(r7.json()["options"]) >= len(b5["options"])


async def test_conjure_celestial_tier_cr(gm_client):
    """Conjure Celestial uses the non-linear tier: CR 4 at L7/L8, CR 5 at L9
    (a unicorn becomes available at 9th)."""
    r7 = await gm_client.get(
        _URL, params={"spell": "conjure-celestial", "slot_level": 7})
    assert r7.json()["max_cr"] == 4
    r9 = await gm_client.get(
        _URL, params={"spell": "conjure-celestial", "slot_level": 9})
    assert r9.json()["max_cr"] == 5
    assert "unicorn" in {o["slug"] for o in r9.json()["options"]}


async def test_unknown_spell_400(gm_client):
    r = await gm_client.get(_URL, params={"spell": "fireball", "count": 8})
    assert r.status_code == 400, r.text


async def test_bad_count_400(gm_client):
    r = await gm_client.get(_URL, params={"spell": "conjure-animals", "count": 3})
    assert r.status_code == 400, r.text
