"""v2.99.250 — H.3 batched 5-Eldritch-Invocation breadth.

Phase H.3 of the v2.99.193 phased completion plan. Ships a
single `/use_invocation` endpoint backed by a 5-entry
registry covering the filed PHB+XGE invocations:
  - Devil's Sight (Lv 2+)
  - Mask of Many Faces (Lv 2+)
  - Hex Warrior (Lv 1+, Hexblade prereq)
  - Lifedrinker (Lv 12+, Pact of the Blade prereq)
  - Lance of Lethargy (Lv 2+, Eldritch Blast prereq filed)

v1 ships announce-only — each invocation's deep mechanical
wiring is filed for follow-up commits.

Magnus Hexbinder (Warlock The Fiend Lv 5) is the demo fixture.
Tests PATCH his subclass / pact for prereq cases.

Tests:
  - Devil's Sight happy at Lv 5 → broadcast.
  - Bad slug → 400.
  - Wrong class (Pip Rogue) → 409 wrong_class.
  - Lifedrinker without pact-of-the-blade → 409 pact_prereq_unmet.
  - Lifedrinker at Lv 5 (needs 12) → 409 level_too_low.
  - Hex Warrior without "hexblade" in subclass → 409 subclass_prereq_unmet.
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


def _inv_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "eldritch-invocation"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def test_use_inv_devils_sight_happy(
    gm_client, gm_ws, roster,
):
    """Magnus Lv 5 → Devil's Sight works (min Lv 2)."""
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
        json={
            "character_id": magnus["id"],
            "invocation_slug": "devils-sight",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["invocation_slug"] == "devils-sight"
    assert data["invocation_name"] == "Devil's Sight"
    await asyncio.sleep(0.3)
    feats = _inv_broadcasts(gm_ws, magnus["id"])
    assert feats


async def test_use_inv_bad_slug(
    gm_client, roster,
):
    """Unknown invocation_slug → 400."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
        json={
            "character_id": magnus["id"],
            "invocation_slug": "not-a-real-invocation",
        },
    )
    assert r.status_code == 400, r.text


async def test_use_inv_wrong_class(
    gm_client, roster,
):
    """Pip (Rogue) → 409 wrong_class."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
        json={
            "character_id": pip["id"],
            "invocation_slug": "devils-sight",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_class"


async def test_use_inv_lifedrinker_no_pact(
    gm_client, roster,
):
    """Magnus without pact-of-the-blade → 409 pact_prereq_unmet.
    (Magnus default has no pact_boon set, so this is the
    expected failure.)"""
    magnus = roster["Magnus Hexbinder"]
    # First PATCH level to 12+ so prereq is the pact, not the
    # level.
    await _patch_sheet(
        gm_client, magnus["id"], {"level": 12},
        class_slug="warlock",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
            json={
                "character_id": magnus["id"],
                "invocation_slug": "lifedrinker",
            },
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "pact_prereq_unmet"
    finally:
        await _patch_sheet(
            gm_client, magnus["id"], {"level": 5},
            class_slug="warlock",
        )


async def test_use_inv_lifedrinker_level_too_low(
    gm_client, roster,
):
    """Lifedrinker at Lv 5 (needs 12) → 409 level_too_low."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
        json={
            "character_id": magnus["id"],
            "invocation_slug": "lifedrinker",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 12
    assert data.get("got") == 5


async def test_use_inv_hex_warrior_wrong_subclass(
    gm_client, roster,
):
    """Magnus default subclass is The Fiend (not Hexblade) →
    409 subclass_prereq_unmet."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invocation",
        json={
            "character_id": magnus["id"],
            "invocation_slug": "hex-warrior",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "subclass_prereq_unmet"
