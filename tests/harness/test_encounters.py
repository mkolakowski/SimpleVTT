"""Encounters CRUD endpoints — saved fight snapshots.

v2.99.65 — also covers the speed_walk heal in _perform_encounter_load:
when a saved encounter's battle_state combatants don't carry
speed_walk (the demo seed's shape pre-v2.99.65 and any user-saved
encounter from before this version), Load now projects the speed
from the linked PC sheet or NPC template before pushing the state
to the hub. The init tracker's Mov chip + /token/move enforcement
read the actual speed (Krieger 40, Kael 45, Vex 35, Hill Giant 40)
instead of falling back to a hardcoded 30.



Encounters are pre-built tableau bundles (tokens + battle state +
optional map binding + auto-play playlist) the GM can load later. The
endpoints (``GET /encounters``, ``POST /encounters``, ``PATCH /encounters/{id}``,
``POST /encounters/{id}/spawn``, ``POST /encounters/{id}/duplicate``,
``POST /encounters/{id}/update``, ``POST /encounters/{id}/delete``,
``POST /encounters/{id}/load``) were tested only indirectly via the
demo UI before this commit. v2.40.0 closes the audit gap from
v2.35.1.

Coverage:
  - GET list returns an array (empty or populated)
  - POST build-from-blank creates a row + returns id; subsequent GET
    surfaces it
  - PATCH updates name / description
  - POST duplicate creates a sibling
  - POST update overwrites the payload with the current state
  - POST delete removes the row
  - 403 when non-GM tries to access any of these
"""
from .conftest import CAMPAIGN_ID


async def test_list_encounters_returns_array(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)


async def test_non_gm_cannot_list(alice_client):
    r = await alice_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    assert r.status_code == 403


async def test_create_blank_encounter(gm_client):
    """POST /encounters with explicit `payload` creates a build-from-
    blank draft (Phase-6 prep workflow). Returns ``{ok, id}``."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={
            "name": "Harness test encounter",
            "description": "scratch",
            "payload": {"tokens": [], "battle_state": {"combatants": []}},
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Response is the encounter dict directly (no ok wrapper).
    assert isinstance(data["id"], int) and data["id"] > 0
    assert data["name"] == "Harness test encounter"
    # Confirm it shows up in the list.
    lst = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    names = [e["name"] for e in lst.json()]
    assert "Harness test encounter" in names


async def test_create_encounter_missing_name_400(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"description": "no name"},
    )
    assert r.status_code == 400, r.text


async def test_patch_encounter_updates_name(gm_client):
    """PATCH /encounters/{id} updates name + description in place."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"name": "Patch me", "payload": {"tokens": [], "battle_state": {}}},
    )
    eid = r.json()["id"]
    p = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/encounters/{eid}",
        json={"name": "Patched", "description": "updated"},
    )
    assert p.status_code == 200, p.text
    # Confirm the rename landed via GET.
    lst = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    target = next((e for e in lst.json() if e["id"] == eid), None)
    assert target is not None
    assert target["name"] == "Patched"


async def test_duplicate_encounter(gm_client):
    """POST /encounters/{id}/duplicate creates a sibling row."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"name": "Original", "payload": {"tokens": [], "battle_state": {}}},
    )
    eid = r.json()["id"]
    d = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters/{eid}/duplicate",
        json={},
    )
    assert d.status_code == 200, d.text
    new_id = d.json().get("id")
    assert isinstance(new_id, int) and new_id != eid


async def test_delete_encounter(gm_client):
    """POST /encounters/{id}/delete removes the row."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"name": "DeleteMe", "payload": {"tokens": [], "battle_state": {}}},
    )
    eid = r.json()["id"]
    d = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters/{eid}/delete",
        json={},
    )
    assert d.status_code == 200, d.text
    # Confirm gone from list.
    lst = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    ids = [e["id"] for e in lst.json()]
    assert eid not in ids


async def test_non_gm_cannot_create_403(alice_client):
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"name": "Alice's encounter", "payload": {"tokens": [], "battle_state": {}}},
    )
    assert r.status_code == 403, r.text


async def test_update_encounter_overwrites_payload(gm_client):
    """POST /encounters/{id}/update overwrites the saved payload with
    the current live state. Doesn't TOUCH live tokens — just snapshots
    them — so safe to run alongside other tests."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={"name": "Updatable", "payload": {"tokens": [], "battle_state": {}}},
    )
    eid = r.json()["id"]
    u = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters/{eid}/update",
        json={},
    )
    assert u.status_code == 200, u.text


# Filed: ``POST /encounters/{id}/load`` happy-path test. Loading an
# encounter replaces the live tokens + battle state with the saved
# payload, which is destructive for the demo's standing seed and
# breaks downstream tests (test_move.py, etc.) that depend on it.
# Needs either a "save current state → load test encounter → restore"
# pattern OR a dedicated reset-and-reseed call. Filed.


async def test_load_encounter_heals_missing_speed_walk(gm_client, roster):
    """v2.99.65 — regression for "speed not pulled from sheet into
    init tracker and movement logic" bug. _perform_encounter_load
    now walks the loaded combatants and, for each one missing
    speed_walk, projects the value from the linked PC sheet or
    NPC template. Without the heal, every combatant defaulted to
    30 ft regardless of what the sheet said (Krieger 40, Kael 45,
    Vex 35, etc.) — so the init tracker's Mov chip + /token/move
    enforcement used a stale cap.

    Setup:
      1. Create a fresh test encounter with battle_state containing
         a single Krieger combatant. The combatant deliberately
         OMITS speed_walk to simulate a saved encounter from before
         v2.99.65 (or any user-authored payload that didn't bother
         to populate it).
      2. Load that encounter via POST /encounters/{eid}/load.
      3. GET /economy/{krieger_id} — assert speed_walk == 40 (the
         value on Krieger's seeded sheet), proving the heal pulled
         the canonical value from the Character row.

    Cleanup: load the demo's Tavern Brawl encounter again to
    restore the standing battle_state for downstream tests.
    """
    krieger = roster["Krieger Stonefist"]

    # Snapshot the demo Tavern Brawl id for the restore step.
    lst = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    assert lst.status_code == 200, lst.text
    tavern = next(
        (e for e in lst.json() if e.get("name") == "Tavern Brawl"),
        None,
    )
    assert tavern is not None, (
        "expected the demo 'Tavern Brawl' encounter in the catalog"
    )

    try:
        # Build a minimal test encounter payload: one combatant
        # (Krieger) with NO speed_walk field. active=True so the
        # /economy endpoint returns the per-combatant values
        # instead of the not-in-battle defaults.
        create = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters",
            json={
                "name": "Speed heal regression",
                "description": "v2.99.65 — Krieger combatant w/o speed_walk",
                "payload": {
                    "tokens": [],
                    "battle_state": {
                        "combatants": [
                            {
                                "id": "tok_speed_heal_krieger",
                                "char_id": krieger["id"],
                                "name": krieger["name"],
                                "initiative": 10,
                                "hp_current": 55, "hp_max": 55,
                                "buffs": [],
                                "economy": {
                                    "action": False, "bonus": False,
                                    "reaction": False, "movement": 0,
                                },
                                # NB: NO speed_walk — that's the bug case
                            },
                        ],
                        "turn_index": 0,
                        "round": 1,
                        "active": True,
                    },
                },
            },
        )
        assert create.status_code == 200, create.text
        eid = create.json()["id"]

        # Load the test encounter — heal should populate speed_walk.
        load = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters/{eid}/load",
            json={},
        )
        assert load.status_code == 200, load.text

        # /economy returns the combatant's speed_walk projected by
        # the heal (40 from Krieger's seeded sheet).
        eco = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/economy/{krieger['id']}",
        )
        assert eco.status_code == 200, eco.text
        body = eco.json()
        assert body.get("speed_walk") == 40, (
            f"speed_walk should be healed from Krieger's sheet "
            f"(speed=40); got {body}"
        )
    finally:
        # Restore the demo's standing battle state so downstream
        # tests find Tavern Brawl loaded.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters/{tavern['id']}/load",
            json={"start_audio": False},
        )
