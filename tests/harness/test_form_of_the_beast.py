"""v2.99.368 — Path of the Beast Barbarian: Form of the Beast (G Barbarian batch CLOSE, Lv 3+, TCE).

Phase G Barbarian Paths subclass batch ship #6 — Path of the Beast
opens and CLOSES the Barbarian Paths batch.
RAW TCE p.9: on entering rage, manifest a natural weapon — Bite
(1d8 piercing + self-heal), Claws (1d6 slashing + extra attack),
or Tail (1d8 piercing, 10-ft reach, reaction AC).

v1 announce-only — the natural-weapon attacks + special riders are
GM-tracked. No separate action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Beast Lv 7)
is the demo fixture.

Tests:
  - Lv 7 happy (default claws): 1d6 slashing, reach 5.
  - Lv 7 happy (tail): 1d8 piercing, reach 10.
  - Wrong subclass (default Berserker) → 409.
  - Invalid form → 400.
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


def _fb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_beast(gm_client, roster):
    """PATCH Krieger to Path of the Beast; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Beast"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_fb_happy_claws(
    gm_client, gm_ws, krieger_beast,
):
    """Lv 7 Path of the Beast, default → claws 1d6 slashing."""
    krieger = krieger_beast
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "form-of-the-beast"
    assert data["form"] == "claws"
    assert data["damage_die"] == "1d6"
    assert data["damage_type"] == "slashing"
    assert data["reach_ft"] == 5
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _fb_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["form"] == "claws"


async def test_use_fb_happy_tail(
    gm_client, krieger_beast,
):
    """form=tail → 1d8 piercing, reach 10."""
    krieger = krieger_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "tail"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["form"] == "tail"
    assert data["damage_die"] == "1d8"
    assert data["reach_ft"] == 10


async def test_use_fb_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fb_invalid_form(
    gm_client, krieger_beast,
):
    """Invalid form → 400."""
    krieger = krieger_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "wings"},
    )
    assert r.status_code == 400, r.text
