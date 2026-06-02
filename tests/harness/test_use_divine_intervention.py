"""v2.99.47 — Divine Intervention (Cleric Lv 10/20).

RAW (PHB p.59): "Beginning at 10th level, you can call on your deity
to intervene on your behalf when your need is great. Imploring your
deity's aid requires you to use your action. Describe the assistance
you seek, and roll percentile dice. If you roll a number equal to
or lower than your cleric level, your deity intervenes. ... At 20th
level, your call for intervention succeeds automatically, no roll
required."

Endpoint `/use_divine_intervention` validates Cleric + Lv 10+ + the
daily counter. At Lv 10-19 rolls a d100; success when rolled <=
cleric level. At Lv 20 auto-succeeds (no roll). Atomically
decrements + broadcasts.

v1 simplification: 1/long-rest cooldown regardless of outcome (RAW
says 7-day cooldown on success; filed for multi-day tracker).

Tests use the v2.99.39 capstone-test pattern + the v2.49.12
/api/test/dice/seed to make the d100 roll deterministic at Lv 10.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_at_lv_10(gm_client, roster):
    """Bump Tavik to Lv 10 for the roll-path tests."""
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"class_slug": "cleric", "level": 10},
    )
    yield tavik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"class_slug": "cleric", "level": 8},
    )


@pytest_asyncio.fixture
async def tavik_at_lv_20(gm_client, roster):
    """Bump Tavik to Lv 20 for the auto-success test."""
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"class_slug": "cleric", "level": 20},
    )
    yield tavik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"class_slug": "cleric", "level": 8},
    )


async def _seed_dice(gm_client, seed):
    """Seed the dice RNG so d100 rolls are deterministic."""
    return await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )


async def test_divine_intervention_auto_success_at_lv_20(
    gm_client, gm_ws, tavik_at_lv_20,
):
    """Lv 20 Tavik → auto-success, no roll. Counter decrements +
    feature_used broadcast carries `auto_success: True`.
    """
    tavik = tavik_at_lv_20
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["auto_success"] is True
    assert data["rolled"] is None  # no d100 at Lv 20
    assert data["remaining"] == 0

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    di = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "divine-intervention"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert di, (
        f"expected feature_used(source=divine-intervention); buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    last = di[-1]["data"]
    assert last["auto_success"] is True
    assert last["success"] is True


async def test_divine_intervention_roll_at_lv_10(
    gm_client, gm_ws, tavik_at_lv_10,
):
    """Lv 10 Tavik → d100 rolled. Whatever the outcome, the response
    carries `rolled: int`, `threshold: 10`, and `success` matches
    `rolled <= 10`. Counter decrements regardless.
    """
    tavik = tavik_at_lv_10
    # Seed dice so the d100 is reproducible across runs. Seed 42
    # picks an arbitrary fixed sequence.
    await _seed_dice(gm_client, seed=42)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_success"] is False
    assert isinstance(data["rolled"], int)
    assert 1 <= data["rolled"] <= 100
    assert data["threshold"] == 10
    assert data["success"] == (data["rolled"] <= 10)
    assert data["remaining"] == 0  # counter spent regardless of outcome

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    di = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "divine-intervention"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert di, "expected feature_used broadcast for the roll outcome"
    last = di[-1]["data"]
    assert last["auto_success"] is False
    assert last["rolled"] == data["rolled"]


async def test_divine_intervention_level_too_low(gm_client, roster):
    """Lv 8 Tavik (canonical fixture level) → 409 level_too_low."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "level_too_low"
    assert body["required"] == 10
    assert body["got"] == 8


async def test_divine_intervention_wrong_class(gm_client, roster):
    """Krieger (Barbarian) → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


async def test_divine_intervention_no_uses_left(
    gm_client, tavik_at_lv_20,
):
    """Second invocation same long rest → 409 no_uses_left."""
    tavik = tavik_at_lv_20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["error"] == "no_uses_left"


async def test_divine_intervention_long_rest_refills(
    gm_client, tavik_at_lv_20,
):
    """Spend the daily charge, long rest → second invocation succeeds."""
    tavik = tavik_at_lv_20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert r1.status_code == 200
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_intervention",
        json={"character_id": tavik["id"]},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["auto_success"] is True
