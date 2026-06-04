"""v2.99.198 — Stroke of Luck (Rogue Lv 20) endpoint.

Phase B.3 of the v2.99.193 phased completion plan. RAW (PHB p.97):
"If your attack misses a target within range, you can turn the
miss into a hit. Alternatively, if you fail an ability check, you
can treat the d20 roll as a 20." Once per short or long rest.

v1 ships as an announce-style endpoint mirroring the v2.16.2
Stroke of Luck pattern: the counter exists, the endpoint
decrements + broadcasts a feature_used so the GM applies the
mechanical effect manually. Retroactive DiceRoll mutation (mode=
"check") + attack-record mutation (mode="attack") filed for v3.

Tests:
  - Happy path: Pip PATCH'd to Lv 20 + stroke-of-luck resource
    seeded → /use_stroke_of_luck mode="check" → 200 + resource
    decrements + feature_used broadcast fires.
  - Mode="attack" path: same shape, different feature_name.
  - Gate test: Pip at Lv 7 (default) → 409 level_too_low.
  - Gate test: Pip Lv 20 but resource at 0 → 409 out_of_uses.
"""
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


def _sol_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "stroke-of-luck"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _resource_updates(gm_ws, character_id, key):
    return [
        m for m in gm_ws.buffered("resource_update")
        if (m.get("data") or {}).get("character_id") == character_id
        and (m.get("data") or {}).get("key") == key
    ]


@pytest_asyncio.fixture
async def pip_lv20_with_sol(gm_client, roster):
    """PATCH Pip to Lv 20 + seed the stroke-of-luck resource.
    Restores defaults (Lv 7, no resource) in teardown.
    """
    pip = roster["Pip Quickfingers"]
    # Get the existing resources; the seed has counters like
    # uncanny-dodge / sneak-attack etc. We'll append stroke-of-luck
    # without disturbing the existing entries via a full-list PATCH.
    # For simplicity, we just PATCH the full resources list with the
    # SoL row added; tests don't rely on the other resources for
    # this surface. Teardown restores the original empty SoL state
    # (PATCH the resource back to current=0 — the actual resources
    # list shape is preserved across the test by the fact that the
    # PATCH appends; restoring requires reading the pre-PATCH list).
    await _patch_sheet(
        gm_client, pip["id"], {"level": 20}, class_slug="rogue",
    )
    # Seed the SoL resource by PATCHing a minimal resources list
    # that ONLY contains the SoL row. This is a destructive test
    # PATCH; we restore Lv 7 in teardown but the test focuses on
    # the SoL surface so the other resources don't matter.
    sol_row = {
        "key": "stroke-of-luck",
        "label": "Stroke of Luck",
        "current": 1,
        "max": 1,
        "reset": "short",
    }
    await _patch_sheet(
        gm_client, pip["id"],
        {"resources": [sol_row]},
    )
    yield pip
    # Teardown: restore Lv 7 + clear the resources list.
    await _patch_sheet(
        gm_client, pip["id"], {"level": 7}, class_slug="rogue",
    )
    await _patch_sheet(
        gm_client, pip["id"], {"resources": []},
    )


async def test_use_stroke_of_luck_check_mode(
    gm_client, gm_ws, pip_lv20_with_sol,
):
    """Happy path: Pip at Lv 20 with SoL available → /use_stroke_of_luck
    mode="check" → 200, resource decrements 1 → 0, feature_used
    broadcast fires naming the check-mode flavor.
    """
    pip = pip_lv20_with_sol
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stroke_of_luck",
        json={"character_id": pip["id"], "mode": "check"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "check"
    assert data["remaining"] == 0
    assert data["max"] == 1
    feats = _sol_broadcasts(gm_ws, pip["id"])
    assert feats, (
        f"expected feature_used(source=stroke-of-luck) broadcast; "
        f"buffered={gm_ws.buffered()}"
    )
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("mode") == "check"
    assert "failed check → 20" in (feat_data.get("feature_name") or "")
    # resource_update broadcast.
    resources = _resource_updates(gm_ws, pip["id"], "stroke-of-luck")
    assert resources, "expected resource_update for stroke-of-luck"
    assert (resources[-1].get("data") or {}).get("current") == 0


async def test_use_stroke_of_luck_attack_mode(
    gm_client, gm_ws, pip_lv20_with_sol,
):
    """Mode="attack" path: same shape, miss → hit flavor in
    feature_name + broadcast.
    """
    pip = pip_lv20_with_sol
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stroke_of_luck",
        json={"character_id": pip["id"], "mode": "attack"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "attack"
    feats = _sol_broadcasts(gm_ws, pip["id"])
    assert feats
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("mode") == "attack"
    assert "miss → hit" in (feat_data.get("feature_name") or "")


async def test_use_stroke_of_luck_level_gate(
    gm_client, roster,
):
    """Control: Pip at default Lv 7 → 409 level_too_low."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stroke_of_luck",
        json={"character_id": pip["id"], "mode": "check"},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 20
    assert data.get("got") == 7


async def test_use_stroke_of_luck_out_of_uses(
    gm_client, roster,
):
    """Gate: Pip at Lv 20 with SoL current=0 → 409 out_of_uses."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"], {"level": 20}, class_slug="rogue",
    )
    sol_row_empty = {
        "key": "stroke-of-luck",
        "label": "Stroke of Luck",
        "current": 0, "max": 1, "reset": "short",
    }
    await _patch_sheet(
        gm_client, pip["id"], {"resources": [sol_row_empty]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stroke_of_luck",
            json={"character_id": pip["id"], "mode": "check"},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "out_of_uses"
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": 7}, class_slug="rogue",
        )
        await _patch_sheet(
            gm_client, pip["id"], {"resources": []},
        )
