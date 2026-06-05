"""v2.99.342 — Clockwork Soul: Restore Balance (G.2 batch ship #4, Lv 1+, TCE).

G.2 Sorcerer subclass batch ship #4 — Clockwork Soul opens.
RAW TCE p.69: when a creature you can see within 60 ft is about
to roll a d20 with advantage or disadvantage, use your reaction
to prevent the roll from being affected by advantage and
disadvantage. Uses = proficiency bonus per long rest.

v2.99.344 — deepened past v1 announce-only: the uses-per-long-rest
budget is server-tracked on `sheet.restore_balance_uses` (seeded to
proficiency bonus). Each use decrements; a depleted budget returns
409 `out_of_uses`; the /rest long-rest hook refills it. Reaction.

Tests:
  - Lv 5 happy: range_ft 60, cancels_adv_disadv True, uses 3→2.
  - Exhausted budget (restore_balance_uses=0) → 409 out_of_uses.
  - Wrong subclass (default Zara Draconic) → 409.
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


def _rb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "restore-balance"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_clockwork(gm_client, roster):
    """PATCH Zara to Clockwork Soul; seed the use budget to 3 (Lv 5 PB)."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Clockwork Soul", "restore_balance_uses": 3},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_rb_happy_lv5(
    gm_client, gm_ws, zara_clockwork,
):
    """Lv 5 Clockwork Soul → range 60, cancels adv/disadv, uses 3→2."""
    zara = zara_clockwork
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_restore_balance",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "restore-balance"
    assert data["range_ft"] == 60
    assert data["cancels_adv_disadv"] is True
    assert data["uses_max"] == 3
    assert data["uses_remaining"] == 2
    assert data["sorcerer_level"] == 5
    await asyncio.sleep(0.3)
    feats = _rb_broadcasts(gm_ws, zara["id"])
    assert feats
    assert feats[-1]["data"]["cancels_adv_disadv"] is True
    assert feats[-1]["data"]["uses_remaining"] == 2


async def test_use_rb_out_of_uses(
    gm_client, roster,
):
    """Clockwork Soul with an exhausted budget (0 uses) → 409."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Clockwork Soul", "restore_balance_uses": 0},
        class_slug="sorcerer",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_restore_balance",
            json={"character_id": zara["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "out_of_uses"
        assert data.get("uses_remaining") == 0
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_rb_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_restore_balance",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_rb_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_restore_balance",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
