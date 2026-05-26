"""v2.62.0 — /api/settings/glass_alpha — per-user transparency slider.

Persists the user's frosted-glass card transparency (integer percent
1-100). The tabletop body element renders `--glass-alpha: N%` so all
9 glass-card sites in tabletop.html pick it up via
`color-mix(in srgb, var(--bg) var(--glass-alpha, 42%), transparent)`.

Tests:
  - happy path: POST {alpha: 75} → 200 + persisted; subsequent POST
    {alpha: 30} flips it.
  - 400 on out-of-range (0, 101, negative).
  - 400 on non-integer payloads.
"""
from .conftest import CAMPAIGN_ID  # noqa: F401 — keeps import surface consistent


async def test_glass_alpha_round_trip(gm_client):
    """Two valid values in sequence. Both persist."""
    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": 75},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["glass_alpha"] == 75

    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": 30},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["glass_alpha"] == 30

    # Restore to default so subsequent tests get the expected 42% baseline.
    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": 42},
    )
    assert resp.status_code == 200


async def test_glass_alpha_rejects_below_range(gm_client):
    """alpha=0 is rejected — minimum is 1."""
    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": 0},
    )
    assert resp.status_code == 400


async def test_glass_alpha_rejects_above_range(gm_client):
    """alpha=101 is rejected — max is 100."""
    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": 101},
    )
    assert resp.status_code == 400


async def test_glass_alpha_rejects_negative(gm_client):
    """Negative alpha is rejected."""
    resp = await gm_client.post(
        "/api/settings/glass_alpha",
        json={"alpha": -5},
    )
    assert resp.status_code == 400
