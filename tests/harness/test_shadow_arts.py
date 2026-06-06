"""v2.99.356 — Way of Shadow Monk: Shadow Arts (G Monk Ways batch OPEN, Lv 3+, PHB).

Phase G Monk Ways subclass batch OPEN — Way of Shadow is the first
new way beyond the already-shipped Way of the Open Hand.
RAW PHB p.80: as an action, spend 2 ki to cast Darkness,
Darkvision, Pass without Trace, or Silence without material
components. Also grants the Minor Illusion cantrip.

v1 announce-only — the actual spell effect is GM-tracked. Costs an
action chip + 2 ki.

Kael Brightleaf (Monk, PATCHed to Way of Shadow Lv 7) is the demo
fixture (long-rested so ki is full).

Tests:
  - Lv 7 happy (default darkness): spell darkness, ki_spent 2.
  - Lv 7 happy (silence): spell echoes "silence".
  - Wrong subclass (default Way of the Open Hand) → 409.
  - Invalid spell → 400.
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


def _sa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "shadow-arts"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_shadow(gm_client, roster):
    """PATCH Kael to Way of Shadow + long-rest (full ki); restore
    to Way of the Open Hand on teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of Shadow"},
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


async def test_use_sa_happy_darkness(
    gm_client, gm_ws, kael_shadow,
):
    """Lv 7 Way of Shadow, default → casts Darkness, spends 2 ki."""
    kael = kael_shadow
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_shadow_arts",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "shadow-arts"
    assert data["spell"] == "darkness"
    assert data["ki_spent"] == 2
    assert data["ki_remaining"] >= 0
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _sa_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["spell"] == "darkness"


async def test_use_sa_happy_silence(
    gm_client, kael_shadow,
):
    """spell=silence echoes through."""
    kael = kael_shadow
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_shadow_arts",
        json={"character_id": kael["id"], "spell": "silence",
              "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["spell"] == "silence"


async def test_use_sa_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_shadow_arts",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sa_invalid_spell(
    gm_client, kael_shadow,
):
    """Invalid spell → 400."""
    kael = kael_shadow
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_shadow_arts",
        json={"character_id": kael["id"], "spell": "fireball",
              "override": True},
    )
    assert r.status_code == 400, r.text
