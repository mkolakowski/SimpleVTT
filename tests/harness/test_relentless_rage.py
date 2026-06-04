"""v2.99.202 — Relentless Rage (Barbarian Lv 11+).

Phase F.1 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.49: "Starting at 11th level, your rage can keep you
fighting despite grievous wounds. If you drop to 0 hit points
while you're raging and don't die outright, you can make a DC 10
Constitution saving throw. If you succeed, you drop to 1 hit
point instead. Each time you use this feature after the first,
the DC increases by 5. When you finish a short or long rest, the
DC resets to 10."

Hook lives in `_apply_hp_change` after the v2.99.17 Half-Orc
Relentless Endurance branch. Krieger (Half-Orc Berserker) is the
demo fixture; tests bump him Lv 7 → 11 via PATCH. Since Krieger
has both Relentless Endurance and Relentless Rage at Lv 11, the
test clears the RE resource first so the RR branch can fire.

The broadcast `feature_used(source=relentless-rage)` surfaces
the CON save outcome + DC + next-use DC for the chat card.

Tests:
  - Happy: Krieger Lv 11 + active rage buff + RE spent + at-0
    damage → feature_used(source=relentless-rage) fires + HP=1.
  - Skips below Lv 11.
  - Skips without active rage.
"""
import asyncio
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


async def _set_hp(gm_client, char_id, hp_current):
    await _patch_sheet(
        gm_client, char_id, {"hp": {"current": hp_current}},
    )


def _tok(char, hp_current, hp_max, rage=False):
    buffs = []
    if rage:
        buffs.append({
            "key": "rage", "name": "Rage", "icon": "🐺",
            "concentration": False,
            "duration_rounds": 10, "duration_max": 10,
            "effects": {"resistance_to": ["bludgeoning",
                                          "piercing",
                                          "slashing"]},
        })
    return {
        "id": f"tok_rr_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": buffs,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _rr_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "relentless-rage"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_lv11_no_endurance(gm_client, roster):
    """Bump Krieger to Lv 11 + clear Relentless Endurance resource
    so the Relentless Rage branch is reachable. Restore Lv 7 + the
    RE resource in teardown.
    """
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 11},
        class_slug="barbarian",
    )
    # Clear RE: PATCH the resources list to a row at current=0.
    await _patch_sheet(
        gm_client, krieger["id"],
        {"resources": [
            {"key": "relentless-endurance",
             "label": "Relentless Endurance",
             "current": 0, "max": 1, "reset": "long"},
        ]},
    )
    yield krieger
    await _patch_sheet(
        gm_client, krieger["id"], {"level": 7},
        class_slug="barbarian",
    )
    await _patch_sheet(
        gm_client, krieger["id"],
        {"resources": [
            {"key": "relentless-endurance",
             "label": "Relentless Endurance",
             "current": 1, "max": 1, "reset": "long"},
        ], "relentless_rage_dc": 10},
    )


async def test_relentless_rage_fires_on_dying_transition(
    gm_client, gm_ws, krieger_lv11_no_endurance, roster,
):
    """Krieger Lv 11 + active rage buff + RE spent + Pip hits him
    to 0 HP → feature_used(source=relentless-rage) broadcast +
    Krieger stays at HP=1.
    """
    krieger = krieger_lv11_no_endurance
    pip = roster["Pip Quickfingers"]
    await _set_hp(gm_client, krieger["id"], 3)
    await _seed_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(krieger, hp_current=3, hp_max=60, rage=True),
    ])
    gm_ws.mark()
    krieger_tok = f"tok_rr_{krieger['id']}"
    hit_landed = False
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,  # Pip's Shortsword
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            hit_landed = True
            break
    assert hit_landed, "no hit dealing ≥3 damage landed in 200 seeds"
    await asyncio.sleep(0.3)
    msgs = _rr_broadcasts(gm_ws, krieger["id"])
    assert msgs, (
        f"v2.99.202: expected feature_used(source=relentless-rage); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    # When the save passes, HP should be clamped to 1.
    rr_data = msgs[-1].get("data") or {}
    if rr_data.get("passed"):
        hp_msgs = [
            m for m in gm_ws.buffered("character_hp_update")
            if (m.get("data") or {}).get("character_id") == krieger["id"]
        ]
        assert hp_msgs
        last_hp = (hp_msgs[-1].get("data") or {}).get("hp") or {}
        assert last_hp.get("current") == 1, (
            f"v2.99.202: passed save should clamp HP to 1; got {last_hp}"
        )
    # DC field should be set + at least 10 on the first use.
    assert rr_data.get("dc", 0) >= 10
    assert rr_data.get("next_dc", 0) == rr_data["dc"] + 5


async def test_relentless_rage_skips_below_lv11(
    gm_client, gm_ws, roster,
):
    """Control: Krieger at Lv 7 (default) → no relentless-rage
    broadcast on dying transition.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    await _set_hp(gm_client, krieger["id"], 3)
    await _seed_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(krieger, hp_current=3, hp_max=60, rage=True),
    ])
    gm_ws.mark()
    krieger_tok = f"tok_rr_{krieger['id']}"
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            break
    await asyncio.sleep(0.3)
    msgs = _rr_broadcasts(gm_ws, krieger["id"])
    assert not msgs, (
        f"v2.99.202: Relentless Rage shouldn't fire at Lv 7; "
        f"got {msgs}"
    )


async def test_relentless_rage_skips_without_active_rage(
    gm_client, gm_ws, krieger_lv11_no_endurance, roster,
):
    """Krieger Lv 11 + RE spent but NO active rage → no broadcast."""
    krieger = krieger_lv11_no_endurance
    pip = roster["Pip Quickfingers"]
    await _set_hp(gm_client, krieger["id"], 3)
    await _seed_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(krieger, hp_current=3, hp_max=60, rage=False),
    ])
    gm_ws.mark()
    krieger_tok = f"tok_rr_{krieger['id']}"
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            break
    await asyncio.sleep(0.3)
    msgs = _rr_broadcasts(gm_ws, krieger["id"])
    assert not msgs, (
        f"v2.99.202: Relentless Rage shouldn't fire without "
        f"active rage; got {msgs}"
    )
