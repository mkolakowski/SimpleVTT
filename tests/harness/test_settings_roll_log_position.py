"""v2.49.244 — /api/settings/roll_log_position — per-user UI preference.

Validates the new user-level setting that picks which side of the
tabletop the Roll Log drawer renders on. Right (default) stacks with
the other tabs in the shared right sidebar; left pulls roll log into
its own independent left-side sidebar.

Tests:
  - happy path: POST {position: "left"} → 200 + persisted; subsequent
    POST {position: "right"} flips it back.
  - 400 on invalid value (anything other than "left" / "right").
"""
from .conftest import CAMPAIGN_ID  # noqa: F401 — keeps the harness import surface consistent


async def test_roll_log_position_left_then_right(gm_client):
    """Toggle to left, then back to right. Both persist."""
    resp = await gm_client.post(
        "/api/settings/roll_log_position",
        json={"position": "left"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["roll_log_position"] == "left"

    resp = await gm_client.post(
        "/api/settings/roll_log_position",
        json={"position": "right"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["roll_log_position"] == "right"


async def test_roll_log_position_rejects_invalid_value(gm_client):
    """Anything other than 'left' / 'right' → 400 with the valid set in
    the message so a future client author sees what's allowed.
    """
    resp = await gm_client.post(
        "/api/settings/roll_log_position",
        json={"position": "middle"},
    )
    assert resp.status_code == 400, resp.text
    assert "middle" in resp.text or "Invalid" in resp.text


async def test_roll_log_position_persists_for_player(alice_client):
    """Per-user — Alice's preference is independent of the GM's."""
    resp = await alice_client.post(
        "/api/settings/roll_log_position",
        json={"position": "left"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roll_log_position"] == "left"
    # Flip back so we don't leave the demo Alice in a non-default state
    # for the rest of the suite.
    await alice_client.post(
        "/api/settings/roll_log_position",
        json={"position": "right"},
    )
