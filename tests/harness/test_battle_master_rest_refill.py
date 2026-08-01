"""Battle Master — superiority-dice pool refill on rest (plan Phase 2).

`docs/plans/battle-master.md` Phase 2: the superiority-dice pool refills via the
generic `resources[*].reset == "short"` path in `/rest` — a **short** rest
refills `reset: "short"` resources, and a long rest refills short + long. The
maneuver endpoints (v2.99.x) shipped end-to-end but the refill contract had no
harness test; this closes it.

Setup mirrors `test_maneuvering_attack.py`: flip the demo Fighter (Garrik) to
Battle Master with a curated `superiority-dice` resource (`reset: "short"`),
depleted, then rest and assert the pool is back to max.
"""
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


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers.",
        "manual": False,
    }


def _find_superiority_dice(resources) -> dict | None:
    for r in (resources or []):
        if r.get("key") == "superiority-dice":
            return r
    return None


async def _rest_and_read_pool(gm_client, char_id, rest_type):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": rest_type},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "resources" in data, f"/rest response missing resources: {data}"
    sd = _find_superiority_dice(data["resources"])
    assert sd is not None, (
        f"superiority-dice missing from {rest_type}-rest resources: {data['resources']}"
    )
    return sd


async def _run_refill_case(gm_client, roster, *, start_current, rest_type):
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(start_current, 4)],
        },
        class_slug="fighter",
    )
    try:
        sd = await _rest_and_read_pool(gm_client, garrik["id"], rest_type)
        assert sd["current"] == sd["max"] == 4, (
            f"a {rest_type} rest should refill superiority-dice to max; got {sd}"
        )
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


async def test_short_rest_refills_superiority_dice(gm_client, roster):
    """Depleted 1/4 → a SHORT rest refills the pool to 4/4 (the Phase-2
    deliverable — `reset: "short"` resources come back on a short rest)."""
    await _run_refill_case(gm_client, roster, start_current=1, rest_type="short")


async def test_long_rest_refills_superiority_dice(gm_client, roster):
    """Fully spent 0/4 → a LONG rest also refills the pool to 4/4 (long rest
    covers both short + long reset kinds)."""
    await _run_refill_case(gm_client, roster, start_current=0, rest_type="long")
