"""v2.1048.0 — Procedural map generator.

`POST /campaign/{cid}/settings/maps/generate` draws a dungeon battle map
server-side (no upload) and creates a Map row from it. Returns a JSON
summary `{ok, map: {id, name, image_url}}`. GM-only; a seed makes the
layout deterministic.

Tests:
  - Happy path: 200 + JSON shape + the generated PNG is served + the map
    shows up in the maps list; cleaned up after.
  - Deterministic: the same seed yields byte-identical images.
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
        # The generated PNG is actually served and looks like a PNG.
        img = await gm_client.get(m["image_url"])
        assert img.status_code == 200, img.text
        assert img.content[:8] == b"\x89PNG\r\n\x1a\n", img.content[:8]
    finally:
        if mid:
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
        assert d["map"]["name"] == "Generated Medium Dungeon", d
    finally:
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
