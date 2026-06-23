"""v2.604.0 — PC retirement (Phase 3 of the campaign-pc-archive plan).

Soft-retire endpoints + /characters filtering. Retired characters drop
out of the active listing into the collapsed "Retired" section and are
reversible via /unretire. Owner-only (admins may retire any); distinct
from delete.

Happy path retires + unretires a known demo character (Pip Quickfingers,
owned by demo-alice) and restores it in a `finally` so the shared dev
container is left clean. The signal used to tell "retired" from "active"
is the `/characters/{id}/unretire` form, which only renders in the
Retired section.

See docs/plans/campaign-pc-archive.md.
"""


async def test_retire_moves_to_retired_section_and_unretire_restores(
    alice_client, roster,
):
    pip_id = roster["Pip Quickfingers"]["id"]
    unretire_marker = f'action="/characters/{pip_id}/unretire"'
    try:
        # Baseline: Pip is active — no unretire form on alice's page.
        r = await alice_client.get("/characters", follow_redirects=False)
        assert r.status_code == 200, r.text
        assert unretire_marker not in r.text

        # Retire → 303 back to /characters.
        r = await alice_client.post(
            f"/characters/{pip_id}/retire", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text

        # Now Pip renders in the Retired section (unretire form present).
        r = await alice_client.get("/characters", follow_redirects=False)
        assert r.status_code == 200
        assert "Retired Characters" in r.text
        assert unretire_marker in r.text

        # Unretire → 303.
        r = await alice_client.post(
            f"/characters/{pip_id}/unretire", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text

        # Back to active — the unretire form is gone again.
        r = await alice_client.get("/characters", follow_redirects=False)
        assert r.status_code == 200
        assert unretire_marker not in r.text
    finally:
        # Safety net: never leave Pip retired for other tests.
        await alice_client.post(
            f"/characters/{pip_id}/unretire", follow_redirects=False,
        )


async def test_retire_requires_owner(bob_client, roster):
    """demo-bob (a non-admin player) doesn't own Pip → 403. If a
    regression lets it through, unretire defensively before failing."""
    pip_id = roster["Pip Quickfingers"]["id"]
    r = await bob_client.post(
        f"/characters/{pip_id}/retire", follow_redirects=False,
    )
    if r.status_code != 403:
        await bob_client.post(
            f"/characters/{pip_id}/unretire", follow_redirects=False,
        )
    assert r.status_code == 403, r.text


async def test_retire_unknown_character_404(alice_client):
    r = await alice_client.post(
        "/characters/999999/retire", follow_redirects=False,
    )
    assert r.status_code == 404, r.text


async def test_retire_redirect_flashes_toast(alice_client, roster):
    """v2.605.3 — the retire redirect carries ?flash=retired, and the
    My-Characters page renders a transient confirmation toast for it.
    Restores Pip (unretire) in a `finally`."""
    pip_id = roster["Pip Quickfingers"]["id"]
    try:
        r = await alice_client.post(
            f"/characters/{pip_id}/retire", follow_redirects=False,
        )
        assert r.status_code in (302, 303), r.text
        assert "flash=retired" in r.headers.get("location", "")
        r = await alice_client.get(
            "/characters?flash=retired", follow_redirects=False,
        )
        assert r.status_code == 200
        assert 'id="flash-toast"' in r.text and "Character retired" in r.text
    finally:
        await alice_client.post(
            f"/characters/{pip_id}/unretire", follow_redirects=False,
        )
