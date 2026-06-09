"""v2.99.307 — Swashbuckler Rogue: Fancy Footwork (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #3 (after Thief Fast Hands already
wired + Assassin Assassinate v2.99.306). RAW XGE p.47: when
you make a melee attack against a creature on your turn,
that creature can't make OAs against you for the rest of
your turn.

v1 announce-only — OA-suppression vs the target is
GM-tracked. No chip — passive on melee attack.

Pip (Thief Lv 7) PATCH'd to Swashbuckler.

Tests:
  - Lv 7 Swashbuckler happy → oa_suppressed_until end_of_turn.
  - Optional target_combatant_id passed through.
  - Default Pip (Thief) → 409.
  - Swashbuckler Lv 2 → 409.
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


def _ff_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fancy-footwork"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_swashbuckler(gm_client, roster):
    """PATCH Pip to Swashbuckler subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Swashbuckler"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


async def test_use_ff_happy_lv7(
    gm_client, gm_ws, pip_swashbuckler,
):
    """Lv 7 Swashbuckler → OAs suppressed end_of_turn."""
    pip = pip_swashbuckler
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fancy_footwork",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["oa_suppressed_until"] == "end_of_turn"
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ff_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_ff_with_target(
    gm_client, pip_swashbuckler,
):
    """Optional target_combatant_id passes through."""
    pip = pip_swashbuckler
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fancy_footwork",
        json={"character_id": pip["id"], "target_combatant_id": "tok_test"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == "tok_test"


async def test_use_ff_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fancy_footwork",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ff_level_gate(
    gm_client, roster,
):
    """Swashbuckler Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Swashbuckler", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fancy_footwork",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


def _pc(cid, c, hp=30):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ff_installs_block_buff_on_target(
    gm_client, gm_ws, roster,
):
    """v2.148.0 — Phase 1: when /use_fancy_footwork is called with
    `target_combatant_id`, install a 1-round `fancy-footwork-blocked`
    buff on the target carrying
    `effects.fancy_footwork_blocked_against_char_id = pip.id`. End-to-
    end: PATCH Pip to Swashbuckler, seed Pip + Tavik in battle, call
    /use_fancy_footwork targeting Tavik → assert `buff_installed: True`
    and the `battle_update` broadcast shows Tavik carrying the buff
    with the right effects."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Swashbuckler"},
        class_slug="rogue",
    )
    try:
        tav_tok = f"tok_ff_t_{tavik['id']}"
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [
                _pc(f"tok_ff_p_{pip['id']}", pip),
                _pc(tav_tok, tavik),
            ], "turn_index": 0, "round": 1, "active": True},
        )
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fancy_footwork",
            json={"character_id": pip["id"],
                  "target_combatant_id": tav_tok},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("buff_installed") is True
        await asyncio.sleep(0.3)
        bus = gm_ws.buffered("battle_update")
        assert bus, "no battle_update broadcast received"
        combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
        tav_cb = combs.get(tav_tok)
        assert tav_cb is not None, (
            f"Tavik missing from battle_update; got ids="
            f"{list(combs.keys())}"
        )
        ff_buff = next(
            (b for b in (tav_cb.get("buffs") or [])
             if b.get("key") == "fancy-footwork-blocked"),
            None,
        )
        assert ff_buff is not None, (
            f"FF buff missing from Tavik; got buffs={tav_cb.get('buffs')}"
        )
        effects = ff_buff.get("effects") or {}
        assert int(effects.get(
            "fancy_footwork_blocked_against_char_id") or 0) == int(pip["id"]), (
            f"FF buff should point at Pip's char_id; got effects={effects}"
        )
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )
