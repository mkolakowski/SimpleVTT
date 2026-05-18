"""/api/campaign/{cid}/token/{tid}/move — token move endpoint tests.

Coverage:
  - Happy path with distance_ft computation (Chebyshev on a 70-px
    square grid → 1 cell = 5 ft)
  - 404 unknown token
  - WS broadcast carries from_x/from_y/distance_ft/character_id/
    token_template_id (v2.6.2)

The new GET /api/campaign/{cid}/tokens endpoint (v2.12.1) is what
makes this test viable — we need token IDs + current positions to
compute expected distances.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _tokens_by_char(client) -> dict[int, dict]:
    """Return tokens keyed by character_id (PC tokens) for easy
    lookup. Hidden tokens are filtered out by the server based on
    the client's permissions; the GM sees everything."""
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    by_char = {}
    for t in data["tokens"]:
        if t.get("character_id"):
            by_char[t["character_id"]] = t
    return by_char


async def test_tokens_list(gm_client):
    """GET /tokens returns the demo's tokens with grid metadata."""
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens" in data
    assert isinstance(data["tokens"], list)
    # Demo ships 9 tokens (3 PCs + 6 NPCs); verify at least the PC count.
    pc_tokens = [t for t in data["tokens"] if t.get("character_id")]
    assert len(pc_tokens) >= 3
    # Grid metadata.
    assert data["grid_type"] == "square"
    assert data["grid_size_px"] == 70


async def test_move_pip_one_cell(gm_client, gm_ws, roster):
    """Move Pip's token by 1 grid cell (70 px) → distance_ft = 5.
    Setup-move first to establish a known position, then the real
    move; assert on the response + WS broadcast shape."""
    pip = roster["Pip Quickfingers"]
    tokens = await _tokens_by_char(gm_client)
    assert pip["id"] in tokens, f"No token for Pip in tokens list"
    pip_tok = tokens[pip["id"]]

    # Setup: move to a known starting position. This itself fires a
    # token_move broadcast; clear the WS buffer afterward via mark().
    start_x, start_y = 350.0, 490.0
    setup_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_tok['id']}/move",
        json={"x": start_x, "y": start_y},
    )
    assert setup_resp.status_code == 200
    # Wait briefly for the setup broadcast to land, then clear.
    import asyncio
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Real move: 1 cell to the right (70 px → 5 ft Chebyshev).
    new_x = start_x + 70
    new_y = start_y
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_tok['id']}/move",
        json={"x": new_x, "y": new_y},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["distance_ft"] == 5.0

    msg = await gm_ws.wait_for("token_move")
    assert msg["data"]["id"] == pip_tok["id"]
    assert msg["data"]["distance_ft"] == 5.0
    assert msg["data"]["from_x"] == start_x
    assert msg["data"]["from_y"] == start_y
    assert msg["data"]["x"] == new_x
    assert msg["data"]["y"] == new_y
    assert msg["data"]["character_id"] == pip["id"]


async def test_move_chebyshev_diagonal(gm_client, roster):
    """Diagonal move (70 px x, 70 px y) on a square grid is still 1
    cell of distance (Chebyshev), so distance_ft = 5."""
    pip = roster["Pip Quickfingers"]
    tokens = await _tokens_by_char(gm_client)
    pip_tok = tokens[pip["id"]]
    start_x, start_y = 280.0, 420.0
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_tok['id']}/move",
        json={"x": start_x, "y": start_y},
    )

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_tok['id']}/move",
        json={"x": start_x + 70, "y": start_y + 70},
    )
    assert resp.status_code == 200
    assert resp.json()["distance_ft"] == 5.0


async def test_move_unknown_token(gm_client):
    """Unknown token_id returns 404."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/99999/move",
        json={"x": 0, "y": 0},
    )
    assert resp.status_code == 404
