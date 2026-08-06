"""v2.159.4 — magic-items-automation Phase 8d: server-side line-AoE
geometry. POST /api/campaign/{cid}/battle/line-targets takes a
caster + target combatant and returns the combatants whose tokens
fall within a width-ft band of the segment between them. Used by
the Javelin of Lightning client (and future Lightning Bolt / Burning
Hands UIs) to pre-fill target_combatant_ids automatically.

Tests use the demo's seeded battle + the /token/{id}/move endpoint
to position 4 tokens at known coordinates, exercise the endpoint,
then restore positions in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import live_token_ids


async def _move_token(gm_client, token_id, x, y):
    """Move a token to a fixed pixel coordinate via the existing
    /token/{id}/move endpoint. GM bypasses movement lock + initiative-
    turn enforcement. Passes ``oa_confirmed: true`` to bypass the
    v2.99.55 plan-movement OA-confirm modal — our test moves cross
    the bandit cluster's threat circles and we don't actually want
    to fire those OAs."""
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
    """Locate 4 distinct combatants from the seeded battle, snapshot
    their token positions, reposition them at controlled coordinates
    for the test, then restore positions in teardown.

    Layout:
      A (caster):     (140,  280)  — left side
      B (target):     (980,  280)  — right side, 12 cells (60 ft) east
      C (on line):    (560,  280)  — between A + B, on the line
      D (off line):   (560,  560)  — same x as C, 4 cells (20 ft) south
    """
    state_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    state = (state_resp.json() or {}).get("battle") or {}
    combatants = state.get("combatants") or []
    # Pick 4 distinct combatants that have source_token_id set (every
    # seeded combatant should). Order is not important; we just need 4.
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
        f"the DB; got {len(picks)} of {len(combatants)} combatants. Either "
        f"the seed is missing or the hub's battle state has gone stale "
        f"against the tokens table — restart the container to refresh both."
    )
    a, b, c, d = picks[:4]

    # Snapshot starting positions for restore.
    # We don't have a direct GET /token/{id}; the encounter listing
    # has token positions but parsing it is brittle. Simpler: hold
    # onto the seed-time x/y we'd otherwise lose by writing our own
    # placeholder — but the seeded positions live in the Token table,
    # not on the hub combatant. The cleanest restore is to put them
    # all back at a default spawn position (200, 200 etc.); the demo
    # auto-reseeds on container restart so a "bad" restore washes
    # away. For now write back the v2.4.2 grid positions for the
    # PCs we used (best-effort — see demo_seed.py seed_tokens).
    starts = {
        "tok_thieves_pip": (350, 490),
        "tok_thieves_thal": (420, 560),
    }

    # Move into Phase 8d test layout.
    await _move_token(gm_client, a["source_token_id"], 140, 280)
    await _move_token(gm_client, b["source_token_id"], 980, 280)
    await _move_token(gm_client, c["source_token_id"], 560, 280)
    await _move_token(gm_client, d["source_token_id"], 560, 560)

    yield {"a": a, "b": b, "c": c, "d": d}

    # Teardown: best-effort restore. The next container restart
    # rewipes-and-reseeds anyway (DEMO_RESET_ON_BOOT=true), but
    # neighboring tests in this run can see stale positions. Move
    # all four to a corner so they don't visibly clutter the demo
    # encounter for the next test.
    for tok in (a, b, c, d):
        try:
            await _move_token(gm_client, tok["source_token_id"], 200, 200)
        except AssertionError:
            pass


async def test_line_targets_includes_on_line_combatant(
    gm_client, positioned_combatants,
):
    """v2.159.4: with combatants A→B as the line endpoints + C
    placed on the line, the endpoint returns C in results."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]
    c = positioned_combatants["c"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/line-targets",
        json={
            "caster_combatant_id": a["id"],
            "target_combatant_id": b["id"],
            "width_ft": 5,
            "max_length_ft": 120,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["caster_id"] == a["id"]
    assert body["target_id"] == b["id"]
    result_ids = {r["combatant_id"] for r in (body.get("results") or [])}
    assert c["id"] in result_ids, (
        f"On-line combatant {c['id']} should be in line-targets "
        f"results; got {result_ids}"
    )


async def test_line_targets_excludes_off_line_combatant(
    gm_client, positioned_combatants,
):
    """v2.159.4: D is 4 grid cells (20 ft) perpendicular from the
    line. With width_ft=5 (half-width 2.5 ft), D should NOT be in
    results."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]
    d = positioned_combatants["d"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/line-targets",
        json={
            "caster_combatant_id": a["id"],
            "target_combatant_id": b["id"],
            "width_ft": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert d["id"] not in result_ids, (
        f"Off-line combatant {d['id']} (20 ft perpendicular) should "
        f"NOT be in line-targets results; got {result_ids}"
    )


async def test_line_targets_excludes_caster_and_target(
    gm_client, positioned_combatants,
):
    """v2.159.4: the caster + target are intrinsically on the line
    (they ARE the endpoints) but should be excluded from results —
    they're not "creatures in the line excluding you and the target."
    Even if the caster's token happens to be inside the band, it
    shouldn't appear in results."""
    a = positioned_combatants["a"]
    b = positioned_combatants["b"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/battle/line-targets",
        json={
            "caster_combatant_id": a["id"],
            "target_combatant_id": b["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    result_ids = {r["combatant_id"] for r in (resp.json().get("results") or [])}
    assert a["id"] not in result_ids
    assert b["id"] not in result_ids
