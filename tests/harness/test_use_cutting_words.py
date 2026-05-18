"""/api/campaign/{cid}/use_cutting_words — Lore Bard Lv 3 reaction.

v2.15.7: dedicated endpoint mirrors /use_bardic_inspiration for the
Cutting Words reaction. Lyra (Lv 6 Lore Bard) is the demo's eligible
PC. The endpoint rolls 1d{BI die} server-side, subtracts it from the
target's roll (announce-only — GM applies manually; no roll-time
intercept infrastructure yet), decrements the Bardic Inspiration
resource, marks the reaction slot, and broadcasts a feature_used
roll-log card with the rolled value.

Tests:
  - happy path: Lyra cuts Pip's roll. d8 (Lv 6 < Lv 9 → d8 tier),
    rolled value in 1..8, BI counter decrements, broadcasts fire.
  - happy path (no target): when target_character_id is omitted the
    response carries target_name=None and the broadcast text reads
    "from a creature's roll" generically.
  - 400 missing character_id.
  - 404 unknown character_id.
  - 409 out_of_uses: deplete Lyra's BI counter then call again — the
    classic "no resource left" branch.
  - 409 wrong-class: Pip is a Rogue, has no BI counter, no Lore
    subclass — the eligibility gate returns a 409 not a 404.

The harness uses the GM client (Lyra is GM-owned per the demo seed).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def lyra_full_bi(gm_client, roster):
    """Long rest Lyra to ensure BI is at 3/3 before the test runs.
    Other tests may have depleted her counter; this fixture is the
    cheap refill (RAW short-rest refills BI but the harness's
    long-rest fixture pattern is already established and works).
    """
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


async def test_cutting_words_happy_path(gm_client, gm_ws, lyra_full_bi, roster):
    """Lyra cuts Pip's roll. Asserts: 200 response shape (die=d8 since
    Lv 6 < 9 falls in the d8 tier; rolled value 1..8; target_name=Pip;
    remaining < 3), the feature_used broadcast carries -{N} and target,
    the resource_update broadcast decrements bardic-inspiration.

    Advances the WSCollector cursor past the lyra_full_bi fixture's
    long-rest broadcasts (which themselves fire resource_update for
    bardic-inspiration with current=3 refill) so the post-cut
    wait_for(resource_update) latches onto the cut's decrement
    instead of the rest's refill.
    """
    lyra = lyra_full_bi
    pip = roster["Pip Quickfingers"]
    gm_ws.mark()  # discard the fixture's long-rest broadcasts
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={
            "character_id": lyra["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["die"] == "d8"  # Lv 6 bard → d8 tier (5-9)
    assert 1 <= data["rolled"] <= 8
    assert data["target_name"] == "Pip Quickfingers"
    assert data["target_id"] == pip["id"]
    assert "remaining" in data
    assert data["remaining"] < 3  # decremented from 3

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "cutting-words"
    assert "Cutting Words" in msg["data"]["feature_name"]
    assert f"-{data['rolled']}" in msg["data"]["feature_name"]
    assert "Pip" in msg["data"]["feature_name"]

    ru_msg = await gm_ws.wait_for("resource_update")
    assert ru_msg["data"]["character_id"] == lyra["id"]
    assert ru_msg["data"]["key"] == "bardic-inspiration"
    assert ru_msg["data"]["current"] == data["remaining"]


async def test_cutting_words_no_target(gm_client, gm_ws, lyra_full_bi):
    """target_character_id is optional. When omitted, response carries
    target_name=None and the broadcast reads "from a creature's roll"
    generically. This matches the NPC-not-in-roster case (an enemy
    bandit on the encounter's token list but not a Character row).
    """
    lyra = lyra_full_bi
    gm_ws.mark()  # discard the fixture's long-rest broadcasts
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={"character_id": lyra["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["target_name"] is None
    assert data["target_id"] is None
    assert 1 <= data["rolled"] <= 8

    msg = await gm_ws.wait_for("feature_used")
    assert "creature's roll" in msg["data"]["feature_name"]


async def test_cutting_words_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={},
    )
    assert resp.status_code == 400


async def test_cutting_words_unknown_character(gm_client):
    """character_id that doesn't exist returns 404."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={"character_id": 99999, "override": True},
    )
    assert resp.status_code == 404


async def test_cutting_words_wrong_class(gm_client, roster):
    """Pip is a Rogue — no Bard level, no Lore subclass. The eligibility
    gate returns 409 (not 404 — 404 is reserved for the no-BI-resource
    branch which is moot since the Lv check fires first).
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409
    detail = resp.json().get("detail", "").lower()
    assert "bard" in detail or "lore" in detail


async def test_cutting_words_out_of_uses(gm_client, lyra_full_bi):
    """Drain Lyra's BI counter then call again — 409 out_of_uses."""
    lyra = lyra_full_bi
    # Lyra has 3 BI uses (full from the fixture). Drain them.
    for _ in range(3):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
            json={"character_id": lyra["id"], "override": True},
        )
        assert resp.status_code == 200, resp.text

    # 4th attempt — out of uses
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={"character_id": lyra["id"], "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("error") == "out_of_uses"
