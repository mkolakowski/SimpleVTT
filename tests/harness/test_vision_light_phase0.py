"""v2.704.0 — Vision & Light Phase 0 (docs/plans/vision-and-light.md).

Phase 0 ships the lighting *data model* (no combat behavior yet):
  - `Map.ambient_light` ("bright" | "dim" | "dark", default "bright") set
    via `POST /campaign/{cid}/settings/maps/{map_id}/ambient_light`;
  - per-token light source `Token.light_bright_ft` / `light_dim_ft`
    (default 0/0 = no light) set via the `PATCH /token/{id}` endpoint.
Both are additive + default-preserving, and surfaced on `GET /tokens`
(top-level `ambient_light` + per-token light radii) so the Phase-1
resolver + future canvas lighting can read them.

Tests:
  - Default: a placed token reports light 0/0 and the map ambient is
    "bright" (status quo).
  - PATCH token light radii → clamped + surfaced on GET /tokens.
  - Set map ambient_light → persisted + broadcast; invalid → "bright".
  - Non-GM setting ambient_light → 403.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def placed_token(gm_client, roster):
    """Place a PC token on the active map and return its GET /tokens entry
    (carrying id + map_id + light fields)."""
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0},
    )
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    body = r.json()
    tok = next((t for t in body["tokens"]
                if t.get("character_id") == pip["id"]), None)
    assert tok, "Pip token must exist on the active map"
    return {"token": tok, "map_id": body["map_id"], "ambient": body.get("ambient_light")}


async def test_defaults_preserve_status_quo(gm_client, placed_token):
    """A fresh token emits no light and the map ambient defaults to bright."""
    tok = placed_token["token"]
    assert tok["light_bright_ft"] == 0
    assert tok["light_dim_ft"] == 0
    assert placed_token["ambient"] == "bright"


async def test_patch_token_light_radii(gm_client, placed_token):
    """PATCH /token/{id} sets the light radii (clamped to [0, 240]) and they
    surface on the response + GET /tokens."""
    tok = placed_token["token"]
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}",
        json={"light_bright_ft": 20, "light_dim_ft": 999},  # 999 → clamp 240
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["light_bright_ft"] == 20
    assert data["light_dim_ft"] == 240
    # Confirm it persists on a re-fetch.
    g = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    again = next(t for t in g["tokens"] if t["id"] == tok["id"])
    assert again["light_bright_ft"] == 20 and again["light_dim_ft"] == 240


async def test_set_map_ambient_light(gm_client, gm_ws, placed_token):
    """Setting ambient_light to 'dark' persists + broadcasts; an invalid
    value falls back to 'bright'."""
    map_id = placed_token["map_id"]
    gm_ws.mark()
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": "dark"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ambient_light"] == "dark"
    await asyncio.sleep(0.3)
    evs = [m for m in gm_ws.buffered("map_ambient_light")
           if (m.get("data") or {}).get("map_id") == map_id]
    assert evs and evs[-1]["data"]["ambient_light"] == "dark"
    # GET /tokens reflects the new ambient.
    g = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    assert g["ambient_light"] == "dark"
    # Invalid value → falls back to bright (and restores the demo default).
    r2 = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": "neon"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["ambient_light"] == "bright"


async def test_non_gm_cannot_set_ambient_light(alice_client, placed_token):
    """A non-GM player (Alice) setting ambient_light → 403."""
    map_id = placed_token["map_id"]
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{map_id}/ambient_light",
        json={"ambient_light": "dark"},
    )
    assert r.status_code == 403, r.text
