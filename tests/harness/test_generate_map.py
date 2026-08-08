"""v2.1048.0 — Procedural map generator.

`POST /campaign/{cid}/settings/maps/generate` draws a dungeon battle map
server-side (no upload) and creates a Map row from it. Returns a JSON
summary `{ok, map: {id, name, image_url}}`. GM-only; a seed makes the
layout deterministic.

Tests:
  - Happy path: 200 + JSON shape + the generated PNG is served + the map
    shows up in the maps list; cleaned up after.
  - Deterministic: the same seed yields byte-identical images.
  - Functional walls: the generated Map carries walls + door segments in
    the Maps 2.0 line-of-sight format, and a door toggles open.
  - 400 on an unknown size.
  - 403 for a player.
"""
from .conftest import CAMPAIGN_ID


async def _delete_map(gm_client, mid):
    await gm_client.post(f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/delete")


async def test_generate_creates_map(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"name": "Test Dungeon", "size": "small", "grid_size_px": "70",
              "seed": "42"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    mid = None
    try:
        assert d["ok"] is True, d
        m = d["map"]
        mid = m["id"]
        assert m["name"] == "Test Dungeon"
        assert m["image_url"].startswith("/static/uploads/maps/"), m
        assert m["image_url"].endswith(".png"), m
        # Response reports the generated wall + door counts.
        assert m["walls"] > 0, m
        assert m["doors"] > 0, m
        # The generated PNG is actually served and looks like a PNG.
        img = await gm_client.get(m["image_url"])
        assert img.status_code == 200, img.text
        assert img.content[:8] == b"\x89PNG\r\n\x1a\n", img.content[:8]
    finally:
        if mid:
            await _delete_map(gm_client, mid)


async def test_generate_populates_functional_walls(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"size": "small", "seed": "42"},
    )
    assert r.status_code == 200, r.text
    mid = r.json()["map"]["id"]
    try:
        w = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")
        assert w.status_code == 200, w.text
        walls = w.json()["walls"]
        assert len(walls) > 0, walls
        # Every segment is a valid LOS wall (four pixel endpoints + id).
        for seg in walls:
            assert {"id", "x1", "y1", "x2", "y2"} <= set(seg), seg
        # At least one toggleable door, and toggling it flips `open`.
        doors = [s for s in walls if s.get("door")]
        assert doors, walls
        did = doors[0]["id"]
        assert doors[0]["open"] is False, doors[0]
        t = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/door/{did}/toggle")
        assert t.status_code == 200, t.text
        after = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls")
        opened = [s for s in after.json()["walls"] if s["id"] == did][0]
        assert opened["open"] is True, opened
    finally:
        await _delete_map(gm_client, mid)


async def test_generate_default_name(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"size": "medium"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    mid = d["map"]["id"]
    try:
        assert d["map"]["name"] == "Generated Dungeon", d
    finally:
        await _delete_map(gm_client, mid)


async def test_generate_all_biomes(gm_client):
    """Each biome produces a valid map with walls (caves / wilderness have
    no doors; dungeon / tavern do)."""
    for biome in ("dungeon", "cave", "wilderness", "tavern"):
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
            data={"biome": biome, "size": "small", "seed": "3"},
        )
        assert r.status_code == 200, (biome, r.text)
        m = r.json()["map"]
        try:
            assert m["name"] == f"Generated {biome.title()}", m
            assert m["walls"] > 0, (biome, m)
        finally:
            await _delete_map(gm_client, m["id"])


async def test_generate_bad_biome(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"biome": "spaceship", "size": "small"},
    )
    assert r.status_code == 400, r.text


async def test_generate_density_changes_map(gm_client):
    """Sparse vs dense (same biome + seed) produces different maps; an
    out-of-range density is clamped, not rejected."""
    ids, imgs = [], []
    try:
        for dens in ("0", "100"):
            r = await gm_client.post(
                f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
                data={"biome": "wilderness", "size": "medium",
                      "density": dens, "seed": "5"},
            )
            assert r.status_code == 200, (dens, r.text)
            m = r.json()["map"]
            ids.append(m["id"])
            imgs.append((await gm_client.get(m["image_url"])).content)
        assert imgs[0] != imgs[1], "density should change the map"
        # Out-of-range density is clamped to [0,100], still a 200.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
            data={"biome": "dungeon", "size": "small", "density": "999"},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["map"]["id"])
    finally:
        for mid in ids:
            await _delete_map(gm_client, mid)


async def test_generate_is_deterministic(gm_client):
    ids, imgs = [], []
    try:
        for _ in range(2):
            r = await gm_client.post(
                f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
                data={"size": "small", "grid_size_px": "70", "seed": "12345"},
            )
            assert r.status_code == 200, r.text
            m = r.json()["map"]
            ids.append(m["id"])
            imgs.append((await gm_client.get(m["image_url"])).content)
        assert imgs[0] == imgs[1], "same seed must reproduce the same image"
    finally:
        for mid in ids:
            await _delete_map(gm_client, mid)


async def test_generate_custom_size(gm_client):
    """size=custom honours cols/rows — the served PNG's real dimensions
    equal cols*cell × rows*cell."""
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"size": "custom", "cols": "50", "rows": "40",
              "grid_size_px": "70", "seed": "1"},
    )
    assert r.status_code == 200, r.text
    m = r.json()["map"]
    try:
        img = await gm_client.get(m["image_url"])
        assert img.status_code == 200, img.text
        # PNG IHDR: width/height are big-endian uint32 at bytes 16 and 20.
        width = int.from_bytes(img.content[16:20], "big")
        height = int.from_bytes(img.content[20:24], "big")
        assert width == 50 * 70, width
        assert height == 40 * 70, height
    finally:
        await _delete_map(gm_client, m["id"])


async def test_generate_bad_size(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"size": "colossal"},
    )
    assert r.status_code == 400, r.text


async def test_generate_gm_only(alice_client):
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/generate",
        data={"size": "small"},
    )
    assert r.status_code == 403, r.text
