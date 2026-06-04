"""v2.99.205 — Primal Champion (Barbarian Lv 20).

Phase F.1 final of the v2.99.193 phased completion plan. RAW
PHB p.49: "At 20th level, you embody the power of the wilds.
Your Strength and Constitution scores increase by 4. Your
maximum for those scores is now 24."

v1 ships:
  - `_pc_has_primal_champion(sheet)` — Barbarian Lv 20+ gate.
  - `_primal_champion_stat_bonus(sheet, ability)` — +4 STR/CON
    when gate fires; 0 otherwise.
  - Wired into v2.99.204 Indomitable Might floor: the floor
    reflects effective STR (base + 4) at Lv 20.

Cap-to-24 is sheet-managed today (the sheet edit panel accepts
arbitrary stat values; the +4 surfaces as an effective bonus
when consumers ask for it via the helper).

This test confirms the Indomitable Might floor at Lv 20 reflects
the +4 STR bonus. Krieger has STR 18 by seed; at Lv 20 the floor
is 22 (18 + 4).
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


def _im_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "indomitable-might"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _seed_until_total_below(
    gm_client, character_id, expr, stat_key, stat_ability, floor,
):
    """Find a seed where /roll's total is below `floor`."""
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
        if total < floor:
            return s, total
    raise AssertionError(
        f"Couldn't find seed producing total < {floor}"
    )


async def test_primal_champion_extends_im_floor_at_lv20(
    gm_client, gm_ws, roster,
):
    """Krieger Lv 20 + STR check + low d20 → floored at base STR
    (18) + 4 = 22 instead of 18.
    """
    krieger = roster["Krieger Stonefist"]
    # Discover a seed at Lv 7 where total < 22.
    seed, low_total = await _seed_until_total_below(
        gm_client, krieger["id"], "1d20",
        "Athletics", "STR", floor=22,
    )
    # PATCH to Lv 20.
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 20},
        class_slug="barbarian",
    )
    try:
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
        # Floor should be base STR (18) + 4 (Primal Champion) = 22.
        assert data.get("total") == 22, (
            f"v2.99.205: at Lv 20 the IM floor should be STR + 4 = 22; "
            f"got total={data.get('total')}, "
            f"breakdown={data.get('breakdown')!r}"
        )
        feats = _im_broadcasts(gm_ws, krieger["id"])
        assert feats, (
            f"v2.99.205: expected feature_used(source=indomitable-might) "
            f"to fire at the boosted floor; buffered: {gm_ws.buffered()}"
        )
        feat_data = feats[-1].get("data") or {}
        assert feat_data.get("new_total") == 22
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )


async def test_primal_champion_skips_below_lv20(
    gm_client, gm_ws, roster,
):
    """Control: Krieger Lv 18 → IM floor at base STR (18), not 22."""
    krieger = roster["Krieger Stonefist"]
    seed, low_total = await _seed_until_total_below(
        gm_client, krieger["id"], "1d20",
        "Athletics", "STR", floor=18,
    )
    pre_level = 7
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 18},
        class_slug="barbarian",
    )
    try:
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
        # Floor at Lv 18 is base STR (18), no +4 bonus.
        assert data.get("total") == 18, (
            f"v2.99.205: at Lv 18 (pre-Primal Champion) the IM "
            f"floor should be base STR=18; got total={data.get('total')}"
        )
    finally:
        await _patch_sheet(
            gm_client, krieger["id"], {"level": pre_level},
            class_slug="barbarian",
        )
