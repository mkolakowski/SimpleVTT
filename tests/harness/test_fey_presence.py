"""v2.99.350 — The Archfey Warlock: Fey Presence (G Warlock batch #2, Lv 1+, PHB).

Phase G Warlock patron subclass batch ship #2 — The Archfey opens.
RAW PHB p.109: as an action, each creature in a 10-ft cube makes a
WIS save vs your warlock spell save DC or is charmed OR frightened
(your choice) until the end of your next turn. Once per short or
long rest.

v1 announce-only — the cube targets + WIS saves + once-per-rest
limit are GM-tracked. The save DC is computed server-side. Action
chip.

Magnus Hexbinder (Warlock, PATCHed to The Archfey Lv 5) is the
demo fixture.

Tests:
  - Lv 5 happy (default charmed): save_dc >= 8, effect "charmed".
  - Lv 5 happy (effect=frightened): effect echoes "frightened".
  - Wrong subclass (default The Fiend) → 409.
  - Invalid effect → 400.
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


def _fp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fey-presence"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_archfey(gm_client, roster):
    """PATCH Magnus to The Archfey; restore to The Fiend on teardown."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Archfey"},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_fp_happy_charmed(
    gm_client, gm_ws, magnus_archfey,
):
    """Lv 5 Archfey, default effect → charmed, save DC computed."""
    magnus = magnus_archfey
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fey_presence",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "fey-presence"
    assert data["effect"] == "charmed"
    assert data["cube_ft"] == 10
    assert data["save_dc"] >= 8
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _fp_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["save_dc"] == data["save_dc"]


async def test_use_fp_happy_frightened(
    gm_client, magnus_archfey,
):
    """effect=frightened echoes through."""
    magnus = magnus_archfey
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fey_presence",
        json={"character_id": magnus["id"], "effect": "frightened",
              "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["effect"] == "frightened"


async def test_use_fp_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fey_presence",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fp_invalid_effect(
    gm_client, magnus_archfey,
):
    """effect must be charmed/frightened → 400."""
    magnus = magnus_archfey
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fey_presence",
        json={"character_id": magnus["id"], "effect": "stunned",
              "override": True},
    )
    assert r.status_code == 400, r.text
