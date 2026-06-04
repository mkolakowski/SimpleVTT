"""v2.99.204 — Indomitable Might (Barbarian Lv 18+).

Phase F.1 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.49: "Beginning at 18th level, if your total for a Strength
check is less than your Strength score, you can use that score
in place of the total."

Server-side intercept on `/roll`: when the rolling PC is
Barbarian Lv 18+ AND the roll's `stat_ability` is "STR" AND the
roll isn't a save or attack, the result's total is floored at the
PC's STR score. A `feature_used(source=indomitable-might)`
broadcast surfaces the trigger.

Krieger Stonefist (Half-Orc Berserker, STR 18 default) gets
bumped Lv 7 → 18 via PATCH.

Tests:
  - Happy: at Lv 18 with a low d20 + STR check → floored at STR
    score (18).
  - Control: at Lv 7 (default) → no floor.
  - Control: at Lv 18 but stat_ability="DEX" → no floor (gate is
    STR-only).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _last_roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


def _im_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "indomitable-might"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _seed_until_total_below_str(
    gm_client, character_id, expr, stat_key, stat_ability, str_score,
):
    """Find a seed where /roll's total comes back below str_score.
    """
    for s in range(1, 500):
        await _seed_dice(gm_client, s)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": expr,
                "character_id": character_id,
                "stat_key": stat_key,
                "stat_ability": stat_ability,
                "visibility": "public",
            },
        )
        if r.status_code != 200:
            continue
        total = int(r.json().get("total") or 0)
        if total < str_score:
            return s, total
    raise AssertionError(
        f"Couldn't find a seed producing total < {str_score}"
    )


async def test_indomitable_might_floors_low_str_check(
    gm_client, gm_ws, roster,
):
    """Krieger Lv 18 + low d20 + STR check → total floored at STR
    score (18). The /roll response total comes back at STR_SCORE.
    """
    krieger = roster["Krieger Stonefist"]
    # Default STR on Krieger's seed is 18. Confirm gate fires.
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 18},
        class_slug="barbarian",
    )
    try:
        # Find a seed at Lv 7 first so the response is unmuted.
        await _patch_sheet(
            gm_client, krieger["id"], {"level": 7},
            class_slug="barbarian",
        )
        seed, low_total = await _seed_until_total_below_str(
            gm_client, krieger["id"], "1d20",
            "Athletics", "STR", str_score=18,
        )
        # Now bump to Lv 18 + re-apply the same seed.
        await _patch_sheet(
            gm_client, krieger["id"], {"level": 18},
            class_slug="barbarian",
        )
        await _seed_dice(gm_client, seed)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": "1d20",
                "character_id": krieger["id"],
                "stat_key": "Athletics",
                "stat_ability": "STR",
                "visibility": "public",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Total should be floored at STR score (18). If the d20
        # rolled higher than 18 by chance (not gated by our seed
        # control), the floor doesn't fire — but the discovery
        # loop ran at Lv 7 with the same seed, so the d20 is
        # known to land < 18.
        assert data.get("total") == 18, (
            f"v2.99.204: STR check total should floor at STR score=18; "
            f"got total={data.get('total')}, "
            f"breakdown={data.get('breakdown')!r}"
        )
        feats = _im_broadcasts(gm_ws, krieger["id"])
        assert feats, (
            f"v2.99.204: expected feature_used(source=indomitable-might); "
            f"buffered: {gm_ws.buffered()}"
        )
        feat_data = feats[-1].get("data") or {}
        assert feat_data.get("new_total") == 18
        assert feat_data.get("old_total") == low_total
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )


async def test_indomitable_might_skips_below_lv18(
    gm_client, gm_ws, roster,
):
    """Control: Krieger at Lv 7 → no floor on STR check."""
    krieger = roster["Krieger Stonefist"]
    gm_ws.mark()
    seed, low_total = await _seed_until_total_below_str(
        gm_client, krieger["id"], "1d20",
        "Athletics", "STR", str_score=18,
    )
    # The seed-discovery loop's last call already exercised the
    # no-floor path. Check that broadcast didn't fire.
    feats = _im_broadcasts(gm_ws, krieger["id"])
    assert not feats, (
        f"v2.99.204: Indomitable Might shouldn't fire at Lv 7; "
        f"got {feats}"
    )


async def test_indomitable_might_skips_non_str_check(
    gm_client, gm_ws, roster,
):
    """Control: Krieger Lv 18 + DEX check → no floor (gate is
    STR-ability only).
    """
    krieger = roster["Krieger Stonefist"]
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 18},
        class_slug="barbarian",
    )
    try:
        await _seed_dice(gm_client, 1)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": "1d20",
                "character_id": krieger["id"],
                "stat_key": "Acrobatics",
                "stat_ability": "DEX",
                "visibility": "public",
            },
        )
        assert r.status_code == 200, r.text
        feats = _im_broadcasts(gm_ws, krieger["id"])
        assert not feats, (
            f"v2.99.204: Indomitable Might shouldn't fire on DEX "
            f"checks; got {feats}"
        )
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )
