"""v2.159.17 — exhaustion-levels Phase 1: data + endpoint + long-rest
decrement.

See docs/plans/exhaustion-levels.md. RAW SRD 5.1 exhaustion is 6
cumulative levels; long rest decrements by 1 (v1 simplification — no
food/water gate). Level 6 = death. This phase ships only the data
shape + mutation endpoint + rest hook; the read-site wiring (Lv 1
checks dis, Lv 2/5 speed, Lv 3 attack/save dis, Lv 4 HP-max halved)
lands in Phase 2-3.

Tests cover:
  - Set absolute level via `level` body field.
  - Increment via `delta`.
  - Clamp at 6 (delta over the cap caps to 6, doesn't go higher).
  - Clamp at 0 (negative delta past 0 floors to 0).
  - Long-rest decrement (level 3 → 2 after long rest).
  - Level 6 → death (PC death_saves.status = "dead").
  - Bad body shape (missing both level + delta) → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


@pytest_asyncio.fixture
async def pip_clean(gm_client, pip):
    """Reset pip's exhaustion to 0 + restore HP via long rest so
    each test starts hermetic."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    yield pip
    # Teardown: restore back to 0.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )


async def test_set_exhaustion_absolute(gm_client, pip_clean):
    """Set level=3 directly → returns level 3, sheet mirrors."""
    pip = pip_clean
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["level"] == 3
    assert data["previous"] == 0
    assert data["died"] is False

    # Sheet readback.
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    assert int(sheet.get("exhaustion_level") or 0) == 3


async def test_set_exhaustion_delta(gm_client, pip_clean):
    """Set absolute=2, then delta=+1 → reads 3."""
    pip = pip_clean
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 2},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "delta": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["level"] == 3
    assert data["previous"] == 2


async def test_set_exhaustion_clamps_at_six(gm_client, pip_clean):
    """delta=+99 from level=0 → caps at 6 (and kills)."""
    pip = pip_clean
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "delta": 99},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["level"] == 6
    assert data["died"] is True

    # Sheet readback — death_saves.status = "dead".
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    ds = sheet.get("death_saves") or {}
    assert ds.get("status") == "dead"


async def test_set_exhaustion_clamps_at_zero(gm_client, pip_clean):
    """delta=-99 from level=2 → floors at 0."""
    pip = pip_clean
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 2},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "delta": -99},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["level"] == 0


async def test_long_rest_decrements_exhaustion(gm_client, pip_clean):
    """Set level=3, take a long rest → level drops to 2 (RAW)."""
    pip = pip_clean
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"], "level": 3},
    )
    rest_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    assert rest_resp.status_code == 200, rest_resp.text

    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    assert int(sheet.get("exhaustion_level") or 0) == 2


async def test_long_rest_at_zero_stays_zero(gm_client, pip_clean):
    """Long rest at level=0 keeps level=0 (no underflow)."""
    pip = pip_clean
    rest_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    assert rest_resp.status_code == 200, rest_resp.text

    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    assert int(sheet.get("exhaustion_level") or 0) == 0


async def test_set_exhaustion_missing_body_returns_400(
    gm_client, pip,
):
    """Body missing both `level` and `delta` → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={"character_id": pip["id"]},
    )
    assert resp.status_code == 400, resp.text


async def test_set_exhaustion_both_target_ids_returns_400(
    gm_client, pip,
):
    """Body has both character_id AND combatant_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_exhaustion",
        json={
            "character_id": pip["id"],
            "combatant_id": "tok_test",
            "level": 1,
        },
    )
    assert resp.status_code == 400, resp.text
