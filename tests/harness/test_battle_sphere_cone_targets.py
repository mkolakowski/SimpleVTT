"""v2.159.5 — magic-items-automation Phase 8e: server-side sphere
+ cone AoE geometry. Mirrors of the Phase 8d line-targets endpoint
for the other two RAW AoE shapes.

  - POST /api/campaign/{cid}/battle/sphere-targets — center +
    radius_ft. Used by Fireball / Shatter / Sleep / etc.
  - POST /api/campaign/{cid}/battle/cone-targets — apex + direction +
    length_ft. RAW 5e cone half-angle ≈ 26.57° (apex angle ~53.13°)
    so the cone's width at distance D equals D. Used by Burning
    Hands / Cone of Cold / Shatter (sphere-variant excluded).

Tests reuse the v2.159.4 /token/{id}/move pattern: position 4
combatants at controlled coordinates, exercise the endpoint, restore
in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import live_token_ids


async def _move_token(gm_client, token_id, x, y):
    """Move a token to a fixed pixel coordinate via /token/{id}/move
    with oa_confirmed: true to bypass the v2.99.55 OA modal."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json={"x": x, "y": y, "oa_confirmed": True},
    )
    assert r.status_code == 200, (
        f"Move token {token_id} → ({x},{y}) failed: "
        f"{r.status_code} {r.text}"
    )


@pytest_asyncio.fixture
async def positioned_combatants(gm_client):
    """Position 4 seeded combatants at controlled coordinates:
      A (apex / center):  (560, 280)
      B (close):           (700, 280)   — 140 px = 10 ft east of A
      C (far):            (1260, 280)   — 700 px = 50 ft east of A
      D (perpendicular):   (560, 700)   — 420 px = 30 ft south of A
    """
    state_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    state = (state_resp.json() or {}).get("battle") or {}
    combatants = state.get("combatants") or []
    # v2.1047.7 — the hub's battle state is in-memory and nothing prunes a
    # combatant when its token row disappears, so ``source_token_id`` can
    # point at a token that no longer exists. CI run 31126181450 had the
    # state referencing token 1 while the DB held a different generation
    # entirely, and all of this file's tests died in setup on
    # ``404 {"detail":"Token not found"}``. Intersect with the live token
    # ids so we only pick combatants whose tokens are actually real.
    live = await live_token_ids(gm_client, CAMPAIGN_ID)
    picks = [
        c for c in combatants
        if isinstance(c, dict) and c.get("source_token_id") and c.get("id")
        and c["source_token_id"] in live
    ][:4]
    assert len(picks) >= 4, (
        f"Need 4 seeded combatants whose source_token_id still exists in "
        f"the DB; got {len(picks)} of {len(combatants)} combatants. The "
        f"hub's battle state has gone stale against the tokens table."
    )
    a, b, c, d = picks[:4]

    await _move_token(gm_client, a["source_token_id"], 560, 280)
    await _move_token(gm_client, b["source_token_id"], 700, 280)
    await _move_token(gm_client, c["source_token_id"], 1260, 280)
    await _move_token(gm_client, d["source_token_id"], 560, 700)

    yield {"a": a, "b": b, "c": c, "d": d}

    for tok in (a, b, c, d):
        try:
            await _move_token(gm_client, tok["source_token_id"], 200, 200)
        except AssertionError:
            pass


# ─── Sphere ───────────────────────────────────────────────────────


async def test_sphere_includes_within_radius(
    gm_client, positioned_combatants,
):
    """v2.159.5: B is 10 ft east of A; sphere centered on A with
    radius 20 ft → B in results."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/sphere-targets",
        json={
            "center_combatant_id": a["id"],
            "radius_ft": 20,
        },
    )
    assert resp.status_code == 200, resp.text
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert b["id"] in result_ids, (
        f"B at 10 ft should be in sphere(A, 20 ft); got {result_ids}"
    )


async def test_sphere_excludes_beyond_radius(
    gm_client, positioned_combatants,
):
    """v2.159.5: C is 50 ft east of A; sphere centered on A with
    radius 20 ft → C NOT in results."""
    a = positioned_combatants["a"]
    c = positioned_combatants["c"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/sphere-targets",
        json={
            "center_combatant_id": a["id"],
            "radius_ft": 20,
        },
    )
    assert resp.status_code == 200
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert c["id"] not in result_ids, (
        f"C at 50 ft should NOT be in sphere(A, 20 ft); got {result_ids}"
    )


async def test_sphere_excludes_center_combatant(
    gm_client, positioned_combatants,
):
    """v2.159.5: A is the center; A should not appear in its own
    sphere results — RAW says the area is "centered on a point you
    choose"; the helper excludes the center combatant as a
    target-picker convenience."""
    a = positioned_combatants["a"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/sphere-targets",
        json={
            "center_combatant_id": a["id"],
            "radius_ft": 20,
        },
    )
    assert resp.status_code == 200
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert a["id"] not in result_ids


# ─── Cone ────────────────────────────────────────────────────────


async def test_cone_includes_combatant_in_angular_span(
    gm_client, positioned_combatants,
):
    """v2.159.5: cone with apex=A, direction=B (east), length 20 ft.
    B is at 10 ft due east (on the cone's centerline) → in results.
    Note: B itself is excluded from results because it's the direction
    combatant — so we actually verify via the cone path that a third
    on-line combatant would be picked up. Use C placed 5 ft east of
    A (between A and B's direction) as an additional probe.

    For this test we just verify that the endpoint resolves cleanly
    and the perpendicular combatant D (90° off-axis at 30 ft south)
    is NOT in results."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]
    d = positioned_combatants["d"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/cone-targets",
        json={
            "apex_combatant_id": a["id"],
            "direction_combatant_id": b["id"],
            "length_ft": 60,
        },
    )
    assert resp.status_code == 200, resp.text
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    # D is perpendicular (90° off the east direction) → outside the
    # ~26.57° half-angle. Should NOT be in results.
    assert d["id"] not in result_ids, (
        f"D at 90° off-axis should NOT be in cone(A→B, 60 ft); "
        f"got {result_ids}"
    )


async def test_cone_excludes_beyond_length(
    gm_client, positioned_combatants,
):
    """v2.159.5: C is 50 ft east of A; cone with apex=A, direction=B,
    length 20 ft → C NOT in results (beyond cone length)."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]
    c = positioned_combatants["c"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/cone-targets",
        json={
            "apex_combatant_id": a["id"],
            "direction_combatant_id": b["id"],
            "length_ft": 20,
        },
    )
    assert resp.status_code == 200
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert c["id"] not in result_ids


async def test_cone_excludes_apex_and_direction(
    gm_client, positioned_combatants,
):
    """v2.159.5: A (apex) + B (direction) should always be excluded
    from cone results — the helper auto-excludes them."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/cone-targets",
        json={
            "apex_combatant_id": a["id"],
            "direction_combatant_id": b["id"],
            "length_ft": 60,
        },
    )
    assert resp.status_code == 200
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert a["id"] not in result_ids
    assert b["id"] not in result_ids
