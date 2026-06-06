"""v2.99.359 — Way of the Sun Soul Monk: Radiant Sun Bolt (G Monk Ways batch #5, Lv 3+, XGE).

Phase G Monk Ways subclass batch ship #5 — Way of the Sun Soul
opens.
RAW XGE p.35: ranged spell attack (using DEX) against a target
within 30 ft; on a hit, radiant damage = Martial Arts die + DEX
modifier. (Spend 1 ki for two more bolts as a bonus action.)

v1 announce-only — the attack roll resolution + target choice are
GM-tracked. The attack bonus is computed and the radiant damage is
rolled server-side. Action chip.

Kael Brightleaf (Monk, PATCHed to Way of the Sun Soul Lv 7) is the
demo fixture (Martial Arts die 1d6 at Lv 5-10).

Tests:
  - Lv 7 happy: radiant = max(1, 1d6 + DEX), die 1d6, range 30.
  - Wrong subclass (default Way of the Open Hand) → 409.
  - Wrong class (Caelan paladin) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _rsb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "radiant-sun-bolt"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_sun_soul(gm_client, roster):
    """PATCH Kael to Way of the Sun Soul; restore to Way of the Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Sun Soul"},
        class_slug="monk",
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_rsb_happy_lv7(
    gm_client, gm_ws, kael_sun_soul,
):
    """Lv 7 Sun Soul → radiant = max(1, 1d6 + DEX), range 30."""
    kael = kael_sun_soul
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_radiant_sun_bolt",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "radiant-sun-bolt"
    assert data["martial_arts_die"] == "1d6"
    assert 1 <= data["die_roll"] <= 6
    assert data["radiant_damage"] == max(1, data["die_roll"] + data["dex_mod"])
    assert data["range_ft"] == 30
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _rsb_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["radiant_damage"] == data["radiant_damage"]


async def test_use_rsb_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_radiant_sun_bolt",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_rsb_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_radiant_sun_bolt",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
