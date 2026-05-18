"""Phase 5 multi-user concurrency tests.

The HTTP+WS harness's earlier tests fire one request at a time from
one client. These tests exercise the realtime hub under contention:
multiple authenticated clients firing POSTs concurrently via
``asyncio.gather`` + asserting that every WS recipient receives every
broadcast in some order, with no message loss or hub corruption.

Phase 5 was filed as "stretch" in docs/plans/test-harness.md because
single-user races are the dominant bug class today. This commit
ships the test scaffolding so the multi-user invariants are pinned;
expansion is filed when a multi-user bug actually surfaces.
"""
import asyncio

import httpx
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import WSCollector, open_ws


async def test_concurrent_attacks_both_broadcasts_arrive(
    gm_client, alice_client, gm_ws, alice_ws, roster,
):
    """GM and Alice fire attack POSTs simultaneously. Both WS clients
    must receive BOTH weapon_attack broadcasts (one from each roller).
    Verifies the hub doesn't drop broadcasts under contention."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]

    # asyncio.gather fires both POSTs without awaiting them sequentially —
    # the underlying asyncio event loop interleaves them, which is the
    # closest a single-process test can get to "simultaneous".
    resp_gm, resp_alice = await asyncio.gather(
        gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": tavik["id"], "attack_index": 0, "override": True},
        ),
        alice_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"], "attack_index": 0, "override": True},
        ),
    )
    assert resp_gm.status_code == 200, resp_gm.text
    assert resp_alice.status_code == 200, resp_alice.text

    # Wait for at least the first broadcast on each side, then read the
    # whole buffer to assert count + per-attack identity.
    await gm_ws.wait_for("weapon_attack", timeout=3.0)
    await alice_ws.wait_for("weapon_attack", timeout=3.0)
    # Brief grace so the second broadcast lands too.
    await asyncio.sleep(0.3)

    gm_attacks = gm_ws.buffered("weapon_attack")
    alice_attacks = alice_ws.buffered("weapon_attack")

    assert len(gm_attacks) >= 2, f"GM saw {len(gm_attacks)} attacks, expected ≥2"
    assert len(alice_attacks) >= 2, f"Alice saw {len(alice_attacks)} attacks, expected ≥2"

    gm_names = sorted(m["data"]["caster_char_name"] for m in gm_attacks)
    alice_names = sorted(m["data"]["caster_char_name"] for m in alice_attacks)
    expected = sorted(["Pip Quickfingers", "Brother Tavik Stonebrow"])
    assert gm_names == expected, f"GM names: {gm_names}"
    assert alice_names == expected, f"Alice names: {alice_names}"


async def test_concurrent_rolls_all_arrive(gm_client, gm_ws):
    """Five concurrent /roll calls from the GM. All five broadcasts
    should arrive on the GM's own WS in some order. Asserts no hub
    drop under burst load."""
    N = 5
    posts = [
        gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={"expression": "1d20", "note": f"burst {i}", "visibility": "public"},
        )
        for i in range(N)
    ]
    results = await asyncio.gather(*posts)
    for r in results:
        assert r.status_code == 200, r.text

    # Drain — wait for the first then a grace period for the rest.
    await gm_ws.wait_for("roll", timeout=3.0)
    await asyncio.sleep(0.4)
    rolls = gm_ws.buffered("roll")
    burst_notes = [r["data"]["note"] for r in rolls if r["data"]["note"].startswith("burst ")]
    assert len(burst_notes) == N, f"Expected {N} burst rolls, got {len(burst_notes)}: {burst_notes}"
    assert sorted(burst_notes) == [f"burst {i}" for i in range(N)]


async def test_late_joiner_does_not_get_replay(gm_client, alice_client, gm_ws, roster):
    """Alice does NOT see a broadcast that fired BEFORE her WS
    connected. The hub doesn't replay history to new connections
    (it only sends the current battle_update + presence_update on
    connect, not arbitrary message types)."""
    pip = roster["Pip Quickfingers"]

    # Fire a broadcast BEFORE Alice's WS exists.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "note": "before-alice-connects", "visibility": "public"},
    )
    assert resp.status_code == 200

    # Confirm the GM saw it (control).
    await gm_ws.wait_for("roll", timeout=2.0)
    gm_rolls = [r for r in gm_ws.buffered("roll") if r["data"]["note"] == "before-alice-connects"]
    assert len(gm_rolls) == 1

    # Now open Alice's WS AFTER the broadcast already fired.
    ws = await open_ws(alice_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as alice_late:
            # Wait long enough that any in-flight replay would have arrived.
            await asyncio.sleep(0.5)
            alice_rolls = [r for r in alice_late.buffered("roll") if r["data"]["note"] == "before-alice-connects"]
            assert not alice_rolls, f"Alice (late joiner) saw stale broadcast: {alice_rolls}"
    finally:
        await ws.close()


async def test_late_joiner_does_get_subsequent_broadcasts(
    gm_client, alice_client, roster,
):
    """Inverse of the previous test: a late-joining client DOES
    receive broadcasts that fire AFTER they connect. Sanity-checks
    that the hub isn't accidentally filtering all messages."""
    # Open Alice's WS first this time.
    ws = await open_ws(alice_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws) as alice_ws:
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/roll",
                json={"expression": "1d20", "note": "after-alice-connects", "visibility": "public"},
            )
            assert resp.status_code == 200
            msg = await alice_ws.wait_for("roll", timeout=3.0)
            assert msg["data"]["note"] == "after-alice-connects"
    finally:
        await ws.close()


async def test_multi_tab_same_user_both_receive(alice_client, roster):
    """Open two WS connections as the same user (Alice) — simulates
    Alice with two browser tabs open. Fire a broadcast that should
    reach Alice. BOTH tabs receive it.

    Background: v2.9.1's presence indicator dedupes by user_id so
    Alice's two tabs render as ONE pill. But the underlying WS
    connections are independent, and broadcasts should reach every
    connected socket — multi-tab users shouldn't miss messages just
    because the presence list dedupes them.
    """
    ws1 = await open_ws(alice_client, CAMPAIGN_ID)
    ws2 = await open_ws(alice_client, CAMPAIGN_ID)
    try:
        async with WSCollector(ws1) as a1, WSCollector(ws2) as a2:
            # Alice posts a public roll from her client; both her WS
            # connections should see it.
            resp = await alice_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/roll",
                json={"expression": "1d20", "note": "multi-tab test", "visibility": "public"},
            )
            assert resp.status_code == 200

            msg1 = await a1.wait_for("roll", timeout=3.0)
            msg2 = await a2.wait_for("roll", timeout=3.0)
            assert msg1["data"]["note"] == "multi-tab test"
            assert msg2["data"]["note"] == "multi-tab test"
    finally:
        await ws1.close()
        await ws2.close()
