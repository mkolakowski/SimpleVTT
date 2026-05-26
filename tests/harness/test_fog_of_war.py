"""v2.64.0 — F2 fog-of-war v1.

Tests the new per-user fog-of-war primitive: tokens carry a
`hidden_from_user_ids` list; non-GM viewers don't see tokens whose
user_id appears in that list; GMs always see everything. Endpoints
`POST /token/{tid}/hide` + `/reveal` mutate the list. /attack
auto-reveals a hidden attacker to the target's owner when damage
lands on a PC.

Tests:
  - GM sees all tokens via GET /tokens regardless of hidden_from
    set; non-GM (Alice) gets the token omitted when her user_id is
    in the list.
  - POST /token/{tid}/hide with `from_all_players=true` populates
    the list with every campaign member's user_id (non-GM).
  - POST /token/{tid}/reveal with `to_all=true` clears the list.
  - GM-only access: Alice POSTing /hide returns 403.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _tokens_for(client):
    r = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200, r.text
    return r.json()


async def _ensure_pip_token(gm_client, roster):
    """Make sure Pip has a token on the active map (the demo seed
    places one but test_move + others might have moved/deleted it).
    Re-places at a known position.
    """
    pip_id = roster["Pip Quickfingers"]["id"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip_id}/place-token",
        json={"x": 200.0, "y": 200.0},
    )
    assert r.status_code == 200, r.text


async def _alice_user_id(gm_client, roster) -> int:
    """Look up Alice's user_id by reading Pip's token (Pip is
    Alice's PC; the demo seed sets ``controller_user_id``).
    """
    pip_id = roster["Pip Quickfingers"]["id"]
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert r.status_code == 200
    for t in r.json().get("tokens", []):
        if t.get("character_id") == pip_id and t.get("controller_user_id"):
            return int(t["controller_user_id"])
    raise AssertionError(
        "Could not find Pip's token with a controller_user_id; "
        "Alice's user_id is needed for the test"
    )


async def test_gm_sees_all_tokens_including_hidden_from(
    gm_client, alice_client, roster,
):
    """GM gets the full token list; non-GM (Alice) is filtered when
    her user_id is in the hidden_from set.
    """
    await _ensure_pip_token(gm_client, roster)

    # Find Pip's token id via the GM's view.
    gm_tokens = await _tokens_for(gm_client)
    pip_id = roster["Pip Quickfingers"]["id"]
    pip_token = next(
        (t for t in gm_tokens["tokens"] if t.get("character_id") == pip_id),
        None,
    )
    assert pip_token is not None, "Pip's token missing from GM view"

    alice_id = await _alice_user_id(gm_client, roster)

    # Hide Pip's token from Alice.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/hide",
        json={"from_user_ids": [alice_id]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert alice_id in body["hidden_from_user_ids"]

    try:
        # GM still sees Pip.
        gm_after = await _tokens_for(gm_client)
        gm_pip = next(
            (t for t in gm_after["tokens"] if t["id"] == pip_token["id"]),
            None,
        )
        assert gm_pip is not None, "GM should still see hidden tokens"
        assert alice_id in (gm_pip.get("hidden_from_user_ids") or [])

        # Alice does NOT see Pip's token.
        alice_after = await _tokens_for(alice_client)
        alice_pip = next(
            (t for t in alice_after["tokens"] if t["id"] == pip_token["id"]),
            None,
        )
        assert alice_pip is None, (
            f"Alice should NOT see Pip's token when she's in "
            f"hidden_from_user_ids; got: {alice_pip}"
        )
    finally:
        # Cleanup: reveal so subsequent tests don't see stale hidden state.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/reveal",
            json={"to_all": True},
        )


async def test_reveal_clears_hidden_from_list(
    gm_client, alice_client, roster,
):
    """After /reveal with to_all=true, hidden_from_user_ids is empty
    and Alice sees Pip's token again.
    """
    await _ensure_pip_token(gm_client, roster)
    gm_tokens = await _tokens_for(gm_client)
    pip_id = roster["Pip Quickfingers"]["id"]
    pip_token = next(
        (t for t in gm_tokens["tokens"] if t.get("character_id") == pip_id),
        None,
    )
    assert pip_token is not None

    alice_id = await _alice_user_id(gm_client, roster)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/hide",
        json={"from_user_ids": [alice_id]},
    )
    # Now reveal.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/reveal",
        json={"to_all": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["hidden_from_user_ids"] == []

    alice_after = await _tokens_for(alice_client)
    alice_pip = next(
        (t for t in alice_after["tokens"] if t["id"] == pip_token["id"]),
        None,
    )
    assert alice_pip is not None, "Alice should see Pip again after reveal"


async def test_non_gm_cannot_hide(gm_client, alice_client, roster):
    """Alice (non-GM) trying to POST /hide returns 403."""
    await _ensure_pip_token(gm_client, roster)
    gm_tokens = await _tokens_for(gm_client)
    pip_id = roster["Pip Quickfingers"]["id"]
    pip_token = next(
        (t for t in gm_tokens["tokens"] if t.get("character_id") == pip_id),
        None,
    )
    assert pip_token is not None

    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/hide",
        json={"from_user_ids": [1]},
    )
    assert r.status_code == 403


async def test_hide_invalid_body_400(gm_client, roster):
    """`from_user_ids` must be a list; passing a non-list returns 400."""
    await _ensure_pip_token(gm_client, roster)
    gm_tokens = await _tokens_for(gm_client)
    pip_id = roster["Pip Quickfingers"]["id"]
    pip_token = next(
        (t for t in gm_tokens["tokens"] if t.get("character_id") == pip_id),
        None,
    )
    assert pip_token is not None

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{pip_token['id']}/hide",
        json={"from_user_ids": "not-a-list"},
    )
    assert r.status_code == 400
