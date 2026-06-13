"""v2.227.0 — Periapt of Wound Closure (RAW DMG p.184, uncommon,
attunement): the first magic item to ride the rest-heal substrate.

RAW: "whenever you roll a Hit Die to regain hit points, double the number
of hit points it restores." An equipped+attuned periapt doubles the
short-rest Hit-Die recovery via the new `double_hit_die_healing` field on
the `_equipped_item_effects` substrate, read by the `/rest` endpoint. The
response now carries `hit_die_healing_doubled` (bool) and
`recovered_pre_double` (the pre-doubling roll, or null) so a client can
verify `recovered == 2 × pre` regardless of the HP-cap clamp.

(The periapt's other RAW clause — auto-stabilize when dying at the start of
your turn — is a start-of-turn trigger not modeled in v1.)

Demo fixture: Dame Seraphine Vael (Oath of Vengeance Paladin, d10 HD) wears
an equipped+attuned periapt — her 2nd attuned item (after the Sun Blade).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_PERIAPT_SLUG = "periapt-of-wound-closure"


@pytest_asyncio.fixture
async def seraphine_rested(gm_client, roster):
    """Long-rest Seraphine so she has Hit Dice + HP to recover on the
    subsequent short rest."""
    sera = roster["Dame Seraphine Vael"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text
    return sera


async def test_periapt_doubles_short_rest_hit_die_healing(
    gm_client, seraphine_rested,
):
    """Happy path: Seraphine's short rest doubles the rolled Hit-Die
    recovery — `recovered == 2 × recovered_pre_double`, the flag is set,
    and the breakdown names the periapt."""
    sera = seraphine_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/rest",
        json={"type": "short"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hit_die_healing_doubled"] is True, data
    pre = data["recovered_pre_double"]
    assert isinstance(pre, int) and pre >= 1, data
    assert data["recovered"] == 2 * pre, (
        f"expected doubled recovery {2 * pre}; got {data['recovered']}"
    )
    assert "Periapt of Wound Closure" in (data.get("breakdown") or ""), data


async def test_short_rest_without_periapt_not_doubled(gm_client, roster):
    """Control: a PC with no periapt (Pip) short-rests → not doubled,
    `recovered_pre_double` is null."""
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "short"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hit_die_healing_doubled"] is False, data
    assert data["recovered_pre_double"] is None, data


async def test_periapt_unequip_stops_doubling(gm_client, roster):
    """Unequipping the periapt reverts the doubling. Restores the original
    inventory on teardown."""
    sera = roster["Dame Seraphine Vael"]
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/sheet-json",
    )
    inv = list((sheet_resp.json().get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _PERIAPT_SLUG),
        None,
    )
    assert idx is not None, "Seraphine has no periapt-of-wound-closure item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/sheet-fields",
            json={"inventory": inv},
        )
        # Long-rest to top up HD, then short-rest with the periapt off.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/rest",
            json={"type": "long"},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/rest",
            json={"type": "short"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["hit_die_healing_doubled"] is False, data
        assert data["recovered_pre_double"] is None, data
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{sera['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
