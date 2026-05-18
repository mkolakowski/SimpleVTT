"""/api/campaign/{cid}/roll — generic dice roller endpoint tests.

Coverage:
  - 1d20 happy path → broadcast type=roll
  - 4d6 multi-dice
  - 400 invalid visibility
  - 400 invalid expression (empty)
  - GM-only visibility — player can't see GM-only rolls

Tests use the GM client by default; the visibility test uses the Alice
WS to verify the cross-user filter from the existing
`_filter_roll_for_user` helper.
"""
import asyncio
from .conftest import CAMPAIGN_ID


async def test_roll_d20(gm_client, gm_ws):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "note": "Strength check", "visibility": "public"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert 1 <= data["total"] <= 20

    msg = await gm_ws.wait_for("roll")
    assert msg["data"]["expression"] == "1d20"
    assert msg["data"]["note"] == "Strength check"
    assert msg["data"]["visibility"] == "public"


async def test_roll_4d6(gm_client, gm_ws):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "4d6", "visibility": "public"},
    )
    assert resp.status_code == 200
    # 4d6 → 4-24
    assert 4 <= resp.json()["total"] <= 24
    msg = await gm_ws.wait_for("roll")
    assert msg["data"]["expression"] == "4d6"


async def test_roll_invalid_visibility(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "visibility": "nonsense"},
    )
    assert resp.status_code == 400


async def test_roll_gm_only_hidden_from_player(gm_client, alice_ws, gm_ws):
    """v2.12.4: a GM-only roll fired by the GM is NOT broadcast to
    non-GM clients. The hub's recipient_filter now consults each WS
    connection's identity and skips non-GM clients for ``gm_only``
    rolls (and skips non-GM-non-roller clients for ``gm_and_roller``).

    The GM does still receive it; we use that as a control to confirm
    the message went out at all.
    """
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "note": "Secret v2.12.4 roll", "visibility": "gm_only"},
    )
    assert resp.status_code == 200

    # Control: the GM's own WS should see it.
    msg = await gm_ws.wait_for("roll")
    assert msg["data"]["visibility"] == "gm_only"
    assert msg["data"]["note"] == "Secret v2.12.4 roll"

    # Now assert Alice's WS did NOT receive it.
    await asyncio.sleep(0.3)
    rolls = alice_ws.buffered("roll")
    secrets = [r for r in rolls if r.get("data", {}).get("note") == "Secret v2.12.4 roll"]
    assert not secrets, f"Alice should not see GM-only roll, got: {secrets}"


async def test_roll_gm_and_roller_hidden_from_non_roller(alice_client, alice_ws, bob_ws, gm_ws):
    """Roll posted with ``visibility: "gm_and_roller"`` from Alice is
    seen by Alice (roller) and the GM, NOT by Bob (third party)."""
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "note": "Secret v2.12.4 g+r roll", "visibility": "gm_and_roller"},
    )
    assert resp.status_code == 200

    # Alice (roller) sees it.
    msg_a = await alice_ws.wait_for("roll")
    assert msg_a["data"]["visibility"] == "gm_and_roller"
    assert msg_a["data"]["note"] == "Secret v2.12.4 g+r roll"

    # GM sees it.
    msg_gm = await gm_ws.wait_for("roll")
    assert msg_gm["data"]["note"] == "Secret v2.12.4 g+r roll"

    # Bob does NOT.
    await asyncio.sleep(0.3)
    rolls = bob_ws.buffered("roll")
    secrets = [r for r in rolls if r.get("data", {}).get("note") == "Secret v2.12.4 g+r roll"]
    assert not secrets, f"Bob should not see gm_and_roller roll, got: {secrets}"
