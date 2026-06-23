"""v2.603.0 — campaign archive (Phase 2 of the campaign-pc-archive plan).

Soft-archive endpoints + lobby filtering. Archived campaigns drop out of
the active lobby sections into the collapsed "Archived" section and are
reversible via /unarchive. GM-only; distinct from the admin-only delete.

The happy-path test drives a full round-trip on the demo campaign (id=1)
from a known state. NOTE (v2.605.0): the demo campaign is now seeded
ARCHIVED, so the `finally` restores it to archived (its seed default).
The signal used to tell "archived" from "active" is the presence of the
`/campaign/{id}/unarchive` form, which only renders in the lobby's
Archived section.

See docs/plans/campaign-pc-archive.md.
"""
from .conftest import CAMPAIGN_ID


async def test_archive_unarchive_round_trip(gm_client):
    unarchive_marker = f'action="/campaign/{CAMPAIGN_ID}/unarchive"'
    try:
        # Force a known ACTIVE state (the demo seeds id=1 archived).
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/unarchive", follow_redirects=False,
        )
        r = await gm_client.get("/", follow_redirects=False)
        assert r.status_code == 200, r.text
        assert unarchive_marker not in r.text  # active → no unarchive form

        # Archive → 303 redirect back to the lobby.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text

        # Lobby now renders it in the Archived section (unarchive form present).
        r = await gm_client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "Archived campaigns" in r.text
        assert unarchive_marker in r.text

        # Unarchive → 303 → back to active.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/unarchive", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text
        r = await gm_client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert unarchive_marker not in r.text
    finally:
        # Restore the demo default (id=1 is seeded archived).
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
        )


async def test_archive_requires_gm(alice_client):
    """demo-alice is a player member of campaign 1, not its GM → 403.
    (Guard: if this ever 303s, fail loudly AND unarchive to be safe.)"""
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
    )
    # (No cleanup needed: a 403 means no state change, and the demo seeds
    # id=1 archived anyway.)
    assert r.status_code == 403, r.text


async def test_archive_unknown_campaign_404(gm_client):
    r = await gm_client.post(
        "/campaign/999999/archive", follow_redirects=False,
    )
    assert r.status_code == 404, r.text


async def test_archive_redirect_flashes_toast(gm_client):
    """v2.605.3 — the archive redirect carries ?flash=archived, and the
    lobby renders a transient confirmation toast for it. Restores the
    archived demo default in a `finally`."""
    try:
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text
        assert "flash=archived" in r.headers.get("location", "")
        r = await gm_client.get("/?flash=archived", follow_redirects=False)
        assert r.status_code == 200
        assert 'id="flash-toast"' in r.text and "Campaign archived" in r.text
    finally:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
        )
