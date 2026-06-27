"""v2.99.283 — Ancients Paladin: Undying Sentinel (H.2 deeper).

H.2 Lv 15 first ship — Ancients's "drop to 1 HP not 0" tactic.
RAW PHB p.87: once-per-long-rest; when reduced to 0 HP and not
killed outright, drop to 1 HP instead. Also: no old-age
drawbacks + no magical aging.

**v2.693.0 (Phase 8):** the "drop to 1 HP instead of 0" HP-mutation
is now applied server-side — the endpoint brings the caster up to
exactly 1 HP via `_apply_heal_to_combatant` (Protective Spirit self-
apply shape), flipping the death-save state dying → alive. A misuse
at >0 HP is a no-op heal. The endpoint decrements an
`undying-sentinel` resource (max 1, auto-bootstrapped if missing,
refilled by long rest).

Caelan Lv 7 default → need PATCH to Ancients Lv 15.

Tests:
  - Lv 15 happy → uses_remaining 0, resource decremented.
  - Apply: caster at 0 HP → brought to 1 HP + revived.
  - Wrong subclass → 409.
  - Level gate (Lv 14) → 409.
  - Out of uses → 409 (after the first happy).
  - Long rest refills → uses_remaining 1 after second call.
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


def _us_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "undying-sentinel"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_ancients_lv15(gm_client, roster):
    """PATCH Caelan to Ancients Lv 15 + long-rest to ensure
    Undying Sentinel uses are full."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 15},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_us_happy_lv15(
    gm_client, gm_ws, caelan_ancients_lv15,
):
    """Lv 15 Ancients → uses_remaining 0 after first use."""
    caelan = caelan_ancients_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uses_remaining"] == 0
    assert data["max_uses"] == 1
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _us_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_us_drops_to_one_hp_when_at_zero(
    gm_client, caelan_ancients_lv15,
):
    """v2.693.0 — Phase 8: with the paladin at 0 HP (dying), Undying Sentinel
    brings them up to exactly 1 HP + revives (dying → alive). Set HP to 0 via
    the sheet, then call the endpoint."""
    caelan = caelan_ancients_lv15
    # Drop Caelan to 0 HP (dying) via the sheet-fields HP set.
    r0 = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"hp": {"current": 0}},
    )
    assert r0.status_code == 200, r0.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["hp_after"] == 1, data
    assert data["revived"] is True, data


async def test_use_us_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_us_level_gate(
    gm_client, roster,
):
    """Ancients Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_us_out_of_uses(
    gm_client, caelan_ancients_lv15,
):
    """Second call back-to-back → 409 no_uses_left."""
    caelan = caelan_ancients_lv15
    # First use → 200.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r1.status_code == 200, r1.text
    # Second use without rest → 409.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "no_uses_left"


async def test_use_us_long_rest_refills(
    gm_client, caelan_ancients_lv15,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_ancients_lv15
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r1.status_code == 200, r1.text
    # Long rest refills.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    # Second use after rest → 200, uses_remaining 0 again.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_undying_sentinel",
        json={"character_id": caelan["id"]},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
    assert data["max_uses"] == 1
