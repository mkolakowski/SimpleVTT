"""GM-only Campaign Settings link in the tabletop quick-links drawer.

The tabletop quick-links block (Tools drawer → Quick Links) ships a
Wiki / Characters / Settings / Logout row by default; this commit adds
a GM-gated "Campaign Settings" pill that points at
``/campaign/{cid}/settings`` (the existing GM-only settings page).

Tests:
  - GM loads the tabletop → response body contains the new pill link
    pointed at ``/campaign/{cid}/settings`` AND the "Campaign Settings"
    label.
  - Player loads the tabletop → response body does NOT contain the
    link.
"""
from .conftest import CAMPAIGN_ID


def _expected_href() -> str:
    return f'href="/campaign/{CAMPAIGN_ID}/settings"'


async def test_gm_sees_campaign_settings_quick_link(gm_client):
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert _expected_href() in body, (
        "Expected the GM tabletop to render a quick-links pill linking "
        f"to /campaign/{CAMPAIGN_ID}/settings; not found in response."
    )
    assert "Campaign Settings" in body, (
        "Expected the quick-links pill label 'Campaign Settings' on "
        "the GM tabletop response."
    )


async def test_player_does_not_see_campaign_settings_quick_link(
    alice_client,
):
    resp = await alice_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert _expected_href() not in body, (
        "Player tabletop should NOT contain the GM-only Campaign "
        "Settings quick-link; found it in the response body."
    )
