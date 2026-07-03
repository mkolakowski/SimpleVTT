"""v2.840.0 — the demo maps ship pre-furnished with map-editor elements.

The demo seed (`app/demo_seed.py:seed_map` for the flagship tavern, and
`app/demo_campaigns.py:_apply_map_elements` for the leveled campaigns) runs each
element list through the **same sanitizer the PUT endpoints use** and writes the
JSON columns straight onto the Map. This smoke test guards against those seed
literals drifting out of the stored shape: it discovers the leveled demo
campaigns by name (the flagship, campaign 1, is the shared harness playground
that sibling map tests mutate) and asserts each surfaces well-formed elements
through the `/active-map` bootstrap read.
"""


async def _demo_campaign_ids(gm_client) -> dict[str, int]:
    """Map demo campaign name → id for every campaign the GM owns. Names are
    stable across reseeds even though autoincrement ids are not."""
    r = await gm_client.get("/api/user/gm-campaigns")
    assert r.status_code == 200, r.text
    return {c["name"]: c["id"] for c in r.json()}


async def _active_map(client, cid: int) -> dict:
    r = await client.get(f"/api/campaign/{cid}/active-map")
    assert r.status_code == 200, r.text
    am = r.json()
    assert am.get("map_id"), f"campaign {cid} should have an active map"
    return am


async def test_goblin_warrens_ships_walls_and_hotspots(gm_client):
    cids = await _demo_campaign_ids(gm_client)
    cid = cids.get("Demo L3: The Goblin Warrens")
    assert cid, f"leveled demo campaign missing; saw {list(cids)}"
    am = await _active_map(gm_client, cid)

    walls = am["walls"]
    assert walls, "Goblin Warrens should ship with seeded cave walls + a door"
    for w in walls:
        assert isinstance(w["id"], str) and w["id"]
        for k in ("x1", "y1", "x2", "y2"):
            assert isinstance(w[k], (int, float)), (k, w)
        # Sanitizer-filled defaults are present on every seeded wall.
        assert isinstance(w["door"], bool) and isinstance(w["secret"], bool)
    assert any(w["door"] for w in walls), "expected at least one door"
    assert any(w["secret"] for w in walls), "expected a hidden secret door"

    hotspots = am["hotspots"]
    assert hotspots and hotspots[0]["label"], "expected a labelled hotspot"

    # v2.842.0 — the warren is a dark, torch-lit, fog-explored dungeon.
    assert am["ambient_light"] == "dark", am["ambient_light"]
    assert am["lights"], "expected seeded torch/lantern lights"
    assert am["fog_enabled"] is True, "expected fog of war enabled"
    assert am["fog_revealed"], "expected a revealed fog region over the play area"


async def test_caldera_throne_ships_terrain_lights_labels(gm_client):
    cids = await _demo_campaign_ids(gm_client)
    cid = cids.get("Demo L18: The Dragon's Apotheosis")
    assert cid, f"leveled demo campaign missing; saw {list(cids)}"
    am = await _active_map(gm_client, cid)

    terrain = am["terrain"]
    assert terrain, "Caldera Throne should ship with lava terrain"
    assert any(t["type"] == "lava" for t in terrain)
    for t in terrain:
        for k in ("x", "y", "w", "h"):
            assert isinstance(t[k], (int, float)), (k, t)

    lights = am["lights"]
    assert lights, "expected seeded fire-glow lights"
    for lt in lights:
        for k in ("x", "y", "bright_ft", "dim_ft"):
            assert isinstance(lt[k], (int, float)), (k, lt)
        assert isinstance(lt["color"], str)

    labels = am["labels"]
    assert labels and labels[0]["text"], "expected a public text label"
    assert labels[0]["color"].startswith("#")

    # v2.842.0 — the throne is lit by its own lava (dim ambient).
    assert am["ambient_light"] == "dim", am["ambient_light"]


async def test_demo_elements_visible_to_players(gm_client, alice_client):
    # Walls/lights/labels/terrain are player-visible layers — a non-GM member
    # reads them through the same bootstrap call (GM pins are excluded by
    # design). alice is a member of the L3 campaign.
    cids = await _demo_campaign_ids(gm_client)
    cid = cids["Demo L3: The Goblin Warrens"]
    am = await _active_map(alice_client, cid)
    assert am["walls"], "seeded walls should be visible to players"
    assert "gm_pins" not in am, "GM pins must not leak into the player bootstrap"
