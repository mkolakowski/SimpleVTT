"""State-reset helpers for the encounter-sim suite.

See ``docs/plans/encounter-sim-test-suite.md``'s "Reset strategy"
section. The suite layers three rituals so tests stay isolated
without paying a full lifespan-reset price per test:

  - **Per-test** (cheapest, ~200 ms): ``long_rest_everyone`` — every
    PC's HP → max, slots reset, hit dice partially refilled, buffs
    expire.
  - **Per-file** (~500 ms, not implemented yet): clear the battle
    init + AoE markers + pending casts. Lands when the first Phase 3
    encounter-sim test needs it; reusing the v2.49.x ``reset_battle``
    Phase 1.5 endpoint when it exists.
  - **Per-session**: rely on the demo lifespan auto-reset
    (``DEMO_RESET_ON_BOOT=true``).
"""
from __future__ import annotations

import os

import httpx


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")
CAMPAIGN_ID = int(os.getenv("HARNESS_TEST_CAMPAIGN", "1"))


def _gm_client() -> httpx.Client:
    """ALREADY-OPEN logged-in GM client. Callers must call ``.close()``
    in a try/finally — do NOT wrap in ``with`` because the login call
    has already implicitly opened the client and httpx's context
    manager rejects a second open.
    """
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0)
    resp = client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
    if resp.status_code not in (200, 303):
        client.close()
        raise AssertionError(f"GM login failed: {resp.status_code}")
    return client


def long_rest(char_id: int) -> None:
    """POST ``/rest`` with type=long for one character. The body
    handler restores HP to max, refills spell slots, partially
    refills hit dice. Buffs with duration tied to rest expire.
    """
    client = _gm_client()
    try:
        resp = client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
            json={"type": "long"},
        )
        resp.raise_for_status()
    finally:
        client.close()


def long_rest_everyone(roster: dict) -> None:
    """Long-rest every PC in the demo campaign. Per-test setup hook
    used by smoke tests so each test starts from a fully restored
    party. ~200 ms total for the 12 demo PCs at v2.49.x.
    """
    client = _gm_client()
    try:
        for name, char in roster.items():
            resp = client.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{char['id']}/rest",
                json={"type": "long"},
            )
            if resp.status_code >= 400:
                raise AssertionError(
                    f"long_rest failed for {name} (id={char['id']}): "
                    f"{resp.status_code} {resp.text}"
                )
    finally:
        client.close()
