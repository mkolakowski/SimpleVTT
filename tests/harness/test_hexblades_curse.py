"""v2.99.351 — The Hexblade Warlock: Hexblade's Curse (G Warlock batch #3, Lv 1+, XGE).

Phase G Warlock patron subclass batch ship #3 — The Hexblade opens.
RAW XGE p.55: bonus action, curse a target within 30 ft for 1 min:
+PB damage against it, crit on a 19-20, and on its death regain
HP = warlock level + CHA mod (min 1). Once per short or long rest.

v1 announce-only — the target choice, the +PB/crit-19 attack
riders, the on-death heal, and the once-per-rest limit are
GM-tracked. The bonuses are computed server-side. Bonus chip.

Magnus Hexbinder (Warlock, PATCHed to The Hexblade Lv 5) is the
demo fixture.

Tests:
  - Lv 5 happy: damage_bonus = PB, crit_range 19, death_heal >= 1.
  - Wrong subclass (default The Fiend) → 409.
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


def _hc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hexblades-curse"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_hexblade(gm_client, roster):
    """PATCH Magnus to The Hexblade; restore to The Fiend on teardown."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Hexblade"},
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


async def test_use_hc_happy_lv5(
    gm_client, gm_ws, magnus_hexblade,
):
    """Lv 5 Hexblade → +PB damage, crit 19-20, death heal >= 1."""
    magnus = magnus_hexblade
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hexblades_curse",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "hexblades-curse"
    assert data["range_ft"] == 30
    assert data["damage_bonus"] >= 2  # proficiency bonus (>=2)
    assert data["crit_range"] == 19
    assert data["death_heal"] >= 1
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _hc_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["death_heal"] == data["death_heal"]


async def test_use_hc_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hexblades_curse",
        json={"character_id": magnus["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_hc_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_hexblades_curse",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
