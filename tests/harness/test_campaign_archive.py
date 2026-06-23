"""v2.603.0 — campaign archive (Phase 2 of the campaign-pc-archive plan).

Soft-archive endpoints + lobby filtering. Archived campaigns drop out of
the active lobby sections into the collapsed "Archived" section and are
reversible via /unarchive. GM-only; distinct from the admin-only delete.

The happy-path test archives + unarchives the demo campaign (id=1) and
restores it (unarchive) in a `finally` so the shared dev container is
left clean. The signal used to tell "archived" from "active" is the
presence of the `/campaign/{id}/unarchive` form, which only renders in
the lobby's Archived section.

See docs/plans/campaign-pc-archive.md.
"""
from .conftest import CAMPAIGN_ID


async def test_archive_hides_from_active_lobby_and_unarchive_restores(gm_client):
    unarchive_marker = f'action="/campaign/{CAMPAIGN_ID}/unarchive"'
    try:
        # Baseline: campaign is active — no unarchive form in the lobby.
        r = await gm_client.get("/", follow_redirects=False)
        assert r.status_code == 200, r.text
        assert unarchive_marker not in r.text

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

        # Unarchive → 303.
        r = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/unarchive", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text

        # Back to active — the unarchive form is gone again.
        r = await gm_client.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert unarchive_marker not in r.text
    finally:
        # Safety net: never leave the demo campaign archived for other tests.
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/unarchive", follow_redirects=False,
        )


async def test_archive_requires_gm(alice_client):
    """demo-alice is a player member of campaign 1, not its GM → 403.
    (Guard: if this ever 303s, fail loudly AND unarchive to be safe.)"""
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/archive", follow_redirects=False,
    )
    if r.status_code != 403:
        # Defensive cleanup in case a regression let a non-GM archive it.
        await alice_client.post(
            f"/campaign/{CAMPAIGN_ID}/unarchive", follow_redirects=False,
        )
    assert r.status_code == 403, r.text


async def test_archive_unknown_campaign_404(gm_client):
    r = await gm_client.post(
        "/campaign/999999/archive", follow_redirects=False,
    )
    assert r.status_code == 404, r.text
