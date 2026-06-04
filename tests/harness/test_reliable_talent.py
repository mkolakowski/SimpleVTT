"""v2.99.197 — Reliable Talent (Rogue Lv 11+) floor on proficient skill checks.

Phase B.2 of the v2.99.193 phased completion plan. RAW PHB p.96:
"Whenever you make an ability check that lets you add your
proficiency bonus, you can treat a d20 roll of 9 or lower as a 10."

Server-side intercept on `/roll`: when the rolling PC is a Rogue
Lv 11+ AND the `stat_key` resolves to a proficient skill on the
sheet, the kept d20 is floored to 10 (total + breakdown both
adjusted). A `feature_used(source=reliable-talent)` broadcast
surfaces the trigger for the chat-card.

Tests use the TEST_MODE dice-seeding endpoint (same pattern as
v2.99.13 Halfling Lucky) for determinism. Pip Quickfingers gets
PATCH'd to Lv 11 for the test, restored in finally.
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


def _reliable_talent_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "reliable-talent"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _seed_until_d20_below_10(
    gm_client, gm_ws, character_id, expr, stat_key,
):
    """Pick a dice seed that lands the kept d20 below 10 on a
    /roll using the given expression. Bounded loop; returns the
    seed value used.
    """
    import re
    _re = re.compile(r"\d*d20[^d=+ ]*=(\d+)", re.IGNORECASE)
    for s in range(1, 500):
        await _seed_dice(gm_client, s)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": expr,
                "character_id": character_id,
                "stat_key": stat_key,
                "visibility": "public",
            },
        )
        if r.status_code != 200:
            continue
        bd = r.json().get("breakdown") or ""
        m = _re.search(bd)
        if not m:
            continue
        try:
            d20 = int(m.group(1))
        except ValueError:
            continue
        if 2 <= d20 <= 9:  # exclude natural 1 (Halfling Lucky fires)
            return s, d20
    raise AssertionError("Couldn't find a seed producing 2 <= d20 <= 9")


async def test_reliable_talent_floors_low_d20_on_proficient_skill(
    gm_client, gm_ws, roster,
):
    """Discover a seed at Lv 7 (control: produces d20 in [2,9]
    on Stealth). PATCH Pip to Lv 11; re-seed the same value;
    assert the kept d20 was floored to 10 + feature_used broadcast
    fires.
    """
    pip = roster["Pip Quickfingers"]
    # Step 1: at Lv 7 (default), find a seed that produces d20 in
    # [2,9] (excluding 1 so Halfling Lucky doesn't reroll).
    gm_ws.mark()
    seed, old_d20 = await _seed_until_d20_below_10(
        gm_client, gm_ws, pip["id"], "1d20", "Stealth",
    )
    # Step 2: bump Pip to Lv 11; re-apply the same seed; check the
    # /roll output for the Reliable Talent floor.
    pre_level = 7
    await _patch_sheet(
        gm_client, pip["id"], {"level": 11}, class_slug="rogue",
    )
    try:
        await _seed_dice(gm_client, seed)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll",
            json={
                "expression": "1d20",
                "character_id": pip["id"],
                "stat_key": "Stealth",
                "visibility": "public",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # The response total should be 10 (floored from old_d20).
        assert data.get("total") == 10, (
            f"v2.99.197: Reliable Talent should floor d20={old_d20} "
            f"to 10; got total={data.get('total')}, "
            f"breakdown={data.get('breakdown')!r}"
        )
        feats = _reliable_talent_broadcasts(gm_ws, pip["id"])
        assert feats, (
            f"v2.99.197: expected feature_used(source=reliable-talent) "
            f"for Pip; buffered: {gm_ws.buffered()}"
        )
        feat_data = feats[-1].get("data") or {}
        assert feat_data.get("stat_key") == "Stealth"
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": pre_level},
            class_slug="rogue",
        )


async def test_reliable_talent_skips_below_11(
    gm_client, gm_ws, roster,
):
    """Control: Pip at Lv 7 (default) → Stealth roll with d20 < 10
    → Reliable Talent does NOT fire. The kept d20 is preserved.
    """
    pip = roster["Pip Quickfingers"]
    # Pip is Lv 7 by default — no PATCH needed.
    gm_ws.mark()
    seed, old_d20 = await _seed_until_d20_below_10(
        gm_client, gm_ws, pip["id"], "1d20", "Stealth",
    )
    last_msg = _last_roll(gm_ws)
    assert last_msg is not None
    last_data = last_msg.get("data") or {}
    # d20 below 10 should be preserved (no floor at Lv 7).
    assert last_data.get("total") == old_d20, (
        f"v2.99.197: at Lv 7 Pip shouldn't get Reliable Talent; "
        f"d20={old_d20} should pass through unchanged, got "
        f"total={last_data.get('total')}"
    )
    feats = _reliable_talent_broadcasts(gm_ws, pip["id"])
    assert not feats, (
        f"v2.99.197: Reliable Talent shouldn't fire at Lv 7; "
        f"got {feats}"
    )


async def test_reliable_talent_skips_non_proficient_skill(
    gm_client, gm_ws, roster,
):
    """Pip at Lv 11 makes a check on a non-proficient skill (Religion
    is Wis-based; Pip has CHA/DEX/INT-leaning skills only). Reliable
    Talent should NOT fire.
    """
    pip = roster["Pip Quickfingers"]
    pre_level = 7
    await _patch_sheet(
        gm_client, pip["id"], {"level": 11}, class_slug="rogue",
    )
    try:
        gm_ws.mark()
        seed, old_d20 = await _seed_until_d20_below_10(
            gm_client, gm_ws, pip["id"], "1d20", "Religion",
        )
        last_msg = _last_roll(gm_ws)
        assert last_msg is not None
        last_data = last_msg.get("data") or {}
        assert last_data.get("total") == old_d20, (
            f"v2.99.197: Reliable Talent should NOT fire on a "
            f"non-proficient skill (Religion); d20={old_d20} should "
            f"pass through, got total={last_data.get('total')}"
        )
        feats = _reliable_talent_broadcasts(gm_ws, pip["id"])
        assert not feats, (
            f"v2.99.197: Reliable Talent shouldn't fire on Religion "
            f"(non-proficient); got {feats}"
        )
    finally:
        await _patch_sheet(
            gm_client, pip["id"], {"level": pre_level},
            class_slug="rogue",
        )
