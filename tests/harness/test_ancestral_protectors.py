"""v2.99.366 — Path of the Ancestral Guardian Barbarian: Ancestral Protectors (G Barbarian #3, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #3 — Path of the
Ancestral Guardian opens.
RAW XGE p.9: while raging, the first creature you hit each turn
becomes the target of warrior spirits — until the start of your
next turn it has disadvantage on attacks not against you, and its
targets resist the damage it deals.

v1 announce-only — the disadvantage + resistance effects +
first-hit-per-turn limit are GM-tracked. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Ancestral
Guardian Lv 7) is the demo fixture.

Tests:
  - Lv 7 happy: disadvantage + resistance flags True, broadcast.
  - Wrong subclass (default Berserker) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _ap_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "ancestral-protectors"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_ancestral(gm_client, roster):
    """PATCH Krieger to Path of the Ancestral Guardian; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Ancestral Guardian"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_ap_happy_lv7(
    gm_client, gm_ws, krieger_ancestral,
):
    """Lv 7 Ancestral Guardian → disadvantage + resistance flags."""
    krieger = krieger_ancestral
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "ancestral-protectors"
    assert data["target_attack_disadvantage"] is True
    assert data["target_damage_resisted"] is True
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ap_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["target_attack_disadvantage"] is True


async def test_use_ap_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ap_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


def _pc(cid, c):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ap_install_on_raging_hit(
    gm_client, gm_ws, krieger_ancestral, roster,
):
    """v2.136.0 — Phase 1: when a raging Ancestral Guardian hits a
    creature, install the `ancestral-protectors-mark` buff on the
    target. End-to-end: PATCH Krieger to Ancestral Guardian, rest +
    enter rage, seed battle with Krieger + Pip, POST /attack →
    Greataxe hits Pip → battle_update broadcast shows Pip carrying
    the mark buff with `effects.ancestral_protectors_protected_char_id`
    pointing at Krieger's char_id. The disadvantage half (Phase 1b)
    + resistance half (Phase 2) read this buff at attack/damage time."""
    krieger = krieger_ancestral
    pip = roster["Pip Quickfingers"]
    krieger_tok = f"tok_ap_kri_{krieger['id']}"
    pip_tok = f"tok_ap_pip_{pip['id']}"
    # Long-rest Krieger so rage uses are available.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(krieger_tok, krieger), _pc(pip_tok, pip)],
              "turn_index": 0, "round": 1, "active": True},
    )
    # Enter rage so the install gate passes.
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    # Krieger swings Greataxe at Pip — retry until a hit lands (the
    # default Krieger to-hit +6 vs Pip's AC has a real miss chance per
    # roll; 5 tries gives >99.5% chance of at least one hit).
    hit_resp = None
    for _ in range(5):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": 0,
                  "target_combatant_id": pip_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            hit_resp = r.json()
            break
    assert hit_resp is not None, (
        "Krieger's Greataxe missed Pip on 5 consecutive swings "
        "(very unlikely; check the test fixtures)"
    )
    # On a hit the install hook fires + broadcasts battle_update
    # (the install path of `_install_buff_on_combatant_id`).
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus, "no battle_update broadcast received after Krieger's hit"
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    pip_cb = combs.get(pip_tok)
    assert pip_cb is not None, (
        f"Pip's combatant missing; got ids={list(combs.keys())}"
    )
    mark_buff = next(
        (b for b in (pip_cb.get("buffs") or [])
         if b.get("key") == "ancestral-protectors-mark"),
        None,
    )
    assert mark_buff is not None, (
        f"mark buff missing from Pip after Krieger's hit; got buffs="
        f"{pip_cb.get('buffs')}"
    )
    effects = mark_buff.get("effects") or {}
    assert int(effects.get(
        "ancestral_protectors_protected_char_id") or 0) == int(krieger["id"]), (
        f"mark buff should point at Krieger's char_id; got effects={effects}"
    )
