"""v2.99.361 — Way of the Astral Self Monk: Arms of the Astral Self (G Monk batch #7, Lv 3+, TCE).

Phase G Monk Ways subclass batch ship #7 — Way of the Astral Self
opens.
RAW TCE p.50: bonus action + 1 ki to summon spectral arms for 10
min — unarmed strikes reach 5 ft farther and deal force damage =
Martial Arts die + WIS mod; can use WIS in place of STR.

v1 announce-only — the actual attacks + WIS-for-STR substitution
are GM-tracked. Bonus chip + 1 ki.

Kael Brightleaf (Monk, PATCHed to Way of the Astral Self Lv 7) is
the demo fixture (Martial Arts die 1d6 at Lv 5-10).

Tests:
  - Lv 7 happy: reach +5, die 1d6, duration 10 min, 1 ki spent.
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


def _aa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arms-of-the-astral-self"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_astral(gm_client, roster):
    """PATCH Kael to Way of the Astral Self + long-rest (full ki);
    restore to Way of the Open Hand on teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Astral Self"},
        class_slug="monk",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_aa_happy_lv7(
    gm_client, gm_ws, kael_astral,
):
    """Lv 7 Astral Self → +5 reach, 1d6 force, 10 min, 1 ki spent."""
    kael = kael_astral
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arms_of_the_astral_self",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "arms-of-the-astral-self"
    assert data["reach_bonus_ft"] == 5
    assert data["melee_damage_die"] == "1d6"
    assert data["duration_minutes"] == 10
    assert data["ki_spent"] == 1
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _aa_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["reach_bonus_ft"] == 5


async def test_use_aa_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arms_of_the_astral_self",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aa_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arms_of_the_astral_self",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
