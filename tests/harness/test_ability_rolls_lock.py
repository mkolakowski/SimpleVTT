"""v2.743.0 — GM ability-score reroll lock.

`POST /api/campaign/{cid}/ability-rolls-lock` {locked} (GM-only) toggles
`Campaign.ability_rolls_locked`. When locked, a non-GM owner gets 409 from the
4d6 roller; the GM can always roll; point-buy (client-side) is unaffected.

Pip Quickfingers is owned by demo-alice (a non-GM player), so she exercises
the owner-blocked path.
"""
from .conftest import CAMPAIGN_ID

_LOCK = f"/api/campaign/{CAMPAIGN_ID}/ability-rolls-lock"


async def _roll(client, char_id):
    return await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/roll-abilities")


async def test_reroll_lock_flow(gm_client, alice_client, roster):
    pip = roster["Pip Quickfingers"]
    try:
        # Lock (GM).
        r = await gm_client.post(_LOCK, json={"locked": True})
        assert r.status_code == 200 and r.json()["locked"] is True, r.text

        # The non-GM owner (Alice) is blocked with 409 (not a 403 — she owns
        # Pip, so the lock gate is what stops her).
        a = await _roll(alice_client, pip["id"])
        assert a.status_code == 409, a.text
        assert a.json().get("error") == "ability_rolls_locked"

        # The GM can still roll while locked.
        g = await _roll(gm_client, pip["id"])
        assert g.status_code == 200, g.text

        # Unlock → the owner can roll again.
        u = await gm_client.post(_LOCK, json={"locked": False})
        assert u.status_code == 200 and u.json()["locked"] is False, u.text
        a2 = await _roll(alice_client, pip["id"])
        assert a2.status_code == 200, a2.text
    finally:
        await gm_client.post(_LOCK, json={"locked": False})


async def test_lock_toggle_requires_gm(alice_client):
    r = await alice_client.post(_LOCK, json={"locked": True})
    assert r.status_code == 403, r.text
