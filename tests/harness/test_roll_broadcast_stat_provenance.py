"""v2.99.32 — /roll broadcast carries stat_key + stat_ability +
character_id provenance.

Closes the v2.99.31 client-wiring gap: the BI die banner (in
tabletop.html) needs to know the most recent roll's stat_key /
stat_ability per character to send richer chat-card text to
/use_bardic_inspiration_die. v2.99.32 echoes the v2.99.30 body
fields on the broadcast `roll` event so client-side trackers can
index by character_id.

Tests:
- Body sends stat_key + stat_ability → broadcast carries the same
  fields + character_id.
- Body sends NO stat fields → broadcast carries null for both.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _last_roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def test_roll_broadcast_includes_stat_key_and_ability(
    gm_client, gm_ws, krieger_rested,
):
    """POST /roll with stat_key + stat_ability → broadcast carries
    both fields plus character_id for the v2.99.32 client tracker.
    """
    krieger = krieger_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+7",
            "stat_key": "Athletics",
            "stat_ability": "STR",
            "visibility": "public",
            "character_id": krieger["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    msg = _last_roll(gm_ws)
    assert msg is not None
    d = msg.get("data") or {}
    assert d.get("stat_key") == "Athletics", (
        f"expected stat_key='Athletics' on broadcast; got {d}"
    )
    assert d.get("stat_ability") == "STR", (
        f"expected stat_ability='STR' on broadcast; got {d}"
    )
    assert d.get("character_id") == krieger["id"], (
        f"expected character_id={krieger['id']} on broadcast; got {d}"
    )


async def test_roll_broadcast_omits_stat_fields_when_absent(
    gm_client, gm_ws, krieger_rested,
):
    """Body sends no stat fields → broadcast carries null for both.
    Backward-compatible — existing clients that don't read the new
    fields see no difference.
    """
    krieger = krieger_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "visibility": "public",
            "character_id": krieger["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    msg = _last_roll(gm_ws)
    assert msg is not None
    d = msg.get("data") or {}
    # Either None or missing — both are acceptable shapes.
    assert (d.get("stat_key") is None or d.get("stat_key") == ""), (
        f"expected stat_key None/empty when not sent; got {d.get('stat_key')!r}"
    )
    assert (d.get("stat_ability") is None or d.get("stat_ability") == ""), (
        f"expected stat_ability None/empty when not sent; got {d.get('stat_ability')!r}"
    )
    # character_id should still echo when present.
    assert d.get("character_id") == krieger["id"]
