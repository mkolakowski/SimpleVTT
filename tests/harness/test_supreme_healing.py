"""v2.99.295 — Life Domain Cleric: Supreme Healing (H.1 deeper, Lv 17).

H.1 Lv 17 Life ship. RAW PHB p.61: when you would roll dice
to restore HP with a spell, take the maximum on each die
instead.

v2.143.0 wired the max-dice substitution into the `/cast_spell`
target-bound auto-heal path; v2.1003.0 closes the last gap — the
legacy `/apply_healing` heal-claim (chat-card) path now maxes the
dice too (the filed Phase-1.5 finisher). No chip cost — passive
permanent.

Tavik is Life Domain in the demo (just bumped to Lv 17).

Tests:
  - Lv 17 happy → max_dice_substitution True.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - v2.143.0 — /cast_spell targeted heal maxes dice ([max:8]).
  - v2.1003.0 — /apply_healing claim path maxes dice too.
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


def _sh_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "supreme-healing"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_life_lv17(gm_client, roster):
    """PATCH Tavik to Life Domain Lv 17 (subclass is already
    Life by default — just bump level)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Life Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_sh_happy_lv17(
    gm_client, gm_ws, tavik_life_lv17,
):
    """Lv 17 Life → max_dice_substitution True."""
    tavik = tavik_life_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_dice_substitution"] is True
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _sh_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_sh_wrong_subclass(
    gm_client, roster,
):
    """Light Domain Tavik (PATCH) at Lv 17 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_sh_level_gate(
    gm_client, roster,
):
    """Life Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Life Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_supreme_healing",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_sh_fires_on_cast_spell_heal(
    gm_client, gm_ws, tavik_life_lv17, roster,
):
    """v2.143.0 — Phase 1: when a Life Domain Cleric Lv 17+ casts a
    healing spell, the dice roll at maximum instead of being rolled.
    End-to-end: Tavik PATCHed to Lv 17, casts Cure Wounds at himself
    (target_character_id=tavik.id) → `spell_cast` broadcast carries
    `supreme_healing_applied: True` AND the `heal_breakdown` field
    surfaces the "💗 Supreme Healing" prefix. Per-die value
    deterministically maxed (1d8 → 8) — verified via the breakdown
    string containing `[max:8]`."""
    tavik = tavik_life_lv17
    CURE_WOUNDS_INDEX = 4  # per the existing Tavik fixture comments
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": CURE_WOUNDS_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": tavik["id"],   # self-heal
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Cure Wounds"
    assert d.get("supreme_healing_applied") is True, (
        f"supreme_healing_applied flag should be True; got "
        f"{d.get('supreme_healing_applied')!r}"
    )
    # The 1d8 should resolve to max 8 in the breakdown.
    bd = d.get("auto_heal_breakdown") or ""
    assert "💗 Supreme Healing" in bd, (
        f"Supreme Healing prefix missing from breakdown; got {bd!r}"
    )
    assert "[max:8]" in bd, (
        f"max-die marker missing from breakdown; got {bd!r}"
    )


async def test_sh_fires_on_heal_claim_path(
    gm_client, tavik_life_lv17,
):
    """v2.1003.0 — the legacy `/apply_healing` heal-claim (chat-card)
    path maxes the healing dice for a Lv 17+ Life cleric caster, in
    parity with the v2.143.0 `/cast_spell` auto-heal path. Tavik
    casts Cure Wounds with NO target (claim flow), then the GM claims
    it → `supreme_healing_applied: True`, the breakdown carries the
    💗 prefix + `[max:8]`, and `rolled >= 8` (max die + WIS mod +
    Disciple of Life uplift on top)."""
    tavik = tavik_life_lv17
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    CURE_WOUNDS_INDEX = 4
    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": CURE_WOUNDS_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            # No target — claim flow.
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    cast_id = cast_resp.json()["id"]
    claim_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/apply_healing",
        json={"cast_id": cast_id},
    )
    assert claim_resp.status_code == 200, claim_resp.text
    data = claim_resp.json()
    assert data.get("supreme_healing_applied") is True, data
    bd = data.get("breakdown") or ""
    assert "💗 Supreme Healing" in bd, (
        f"Supreme Healing prefix missing from claim breakdown; got {bd!r}"
    )
    assert "[max:8]" in bd, (
        f"max-die marker missing from claim breakdown; got {bd!r}"
    )
    assert int(data.get("rolled") or 0) >= 8, data
