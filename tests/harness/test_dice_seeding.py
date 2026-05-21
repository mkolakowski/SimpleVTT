"""/api/test/dice/seed — deterministic-dice control surface tests.

The encounter-simulation test suite (docs/plans/encounter-sim-test-
suite.md) needs reproducible dice so assertions like "Fireball 8d6 =
24 fire damage" don't flake. v2.49.12 wires the resolver in
``app/dice.py`` through a shared ``random.Random`` instance and adds
a TEST_MODE-only endpoint that re-seeds it.

This file is the contract test for that endpoint:

  - POST /api/test/dice/seed → 200, seed applied
  - After seeding with the same value twice, the same /roll request
    returns the same total (proves determinism, not just "the server
    accepted the seed").
  - Re-seeding from a different value produces a different total
    (proves the seed actually drives the RNG and isn't, say, ignored).

CI runs this job with ``TEST_MODE=true`` set in the workflow .env so
the router is mounted; production runs without it so the endpoint
404s. We don't test the 404-on-no-TEST_MODE path here because the
harness only ever runs with TEST_MODE on — that's a config invariant,
not something the test layer can flip mid-run.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID


async def _post_seed(gm_client, seed):
    resp = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert resp.status_code == 200, f"seed endpoint returned {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["ok"] is True
    assert body["seed"] == seed


async def _roll(gm_client, expression: str) -> int:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": expression, "visibility": "public"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


async def test_seed_endpoint_accepts_int_seed(gm_client):
    """Happy path: POST with a fixed seed returns 200 + echoes it."""
    await _post_seed(gm_client, 42)


async def test_seed_endpoint_accepts_null_seed(gm_client):
    """Passing seed=None re-seeds from OS entropy (back to non-
    deterministic). The endpoint should still return 200.
    """
    resp = await gm_client.post("/api/test/dice/seed", json={"seed": None})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["seed"] is None


async def test_seeded_rolls_are_reproducible(gm_client):
    """Same seed → same sequence of rolls. We compare two short
    sequences of 4d6 rolls, re-seeding between them with the same
    value, and assert every total matches index-for-index.
    """
    rolls_a: list[int] = []
    await _post_seed(gm_client, 12345)
    for _ in range(4):
        rolls_a.append(await _roll(gm_client, "4d6"))

    rolls_b: list[int] = []
    await _post_seed(gm_client, 12345)
    for _ in range(4):
        rolls_b.append(await _roll(gm_client, "4d6"))

    assert rolls_a == rolls_b, (
        f"Seeded rolls should be deterministic — got {rolls_a} vs {rolls_b}"
    )


async def test_different_seeds_produce_different_rolls(gm_client):
    """Sanity: if reseeding had no effect (e.g. the endpoint was a
    no-op) the prior test would pass on accident. Reseed with a
    different value and assert the sequence diverges somewhere.
    """
    await _post_seed(gm_client, 1)
    seq_one = [await _roll(gm_client, "4d6") for _ in range(4)]

    await _post_seed(gm_client, 2)
    seq_two = [await _roll(gm_client, "4d6") for _ in range(4)]

    assert seq_one != seq_two, (
        f"Different seeds should diverge — both gave {seq_one}"
    )


async def test_seeded_d20_total_in_range(gm_client):
    """Belt-and-braces: confirm seeded output is still a valid 1d20,
    so a regression that returned, say, 0 or 21 would still fail
    the test."""
    await _post_seed(gm_client, 7)
    total = await _roll(gm_client, "1d20")
    assert 1 <= total <= 20, f"1d20 total out of range: {total}"
