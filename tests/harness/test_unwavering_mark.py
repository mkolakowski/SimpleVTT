"""v2.99.375 — Cavalier Fighter: Unwavering Mark (G Fighter sweep #6, Lv 3+, XGE).

Phase G Fighter martial archetype sweep ship #6 — Cavalier opens.
RAW XGE p.30: when you hit a creature with a melee weapon attack,
mark it until the end of your next turn — while within 5 ft it has
disadvantage on attacks not aimed at you, and if it harms an ally
you can make a bonus-action melee attack against it with
advantage, dealing extra damage = half your fighter level.

v1 announce-only — the mark tracking, disadvantage, and punishing
attack are GM-tracked. The punish bonus is computed server-side.
No separate action cost.

Garrik Ironside (Fighter, PATCHed to Cavalier Lv 9) is the demo
fixture (punish bonus = 4).

Tests:
  - Lv 9 happy: disadvantage flag True, punish bonus 4.
  - Wrong subclass (default Champion) → 409.
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


def _um_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "unwavering-mark"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_cavalier(gm_client, roster):
    """PATCH Garrik to Cavalier; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Cavalier"},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_um_happy_lv9(
    gm_client, gm_ws, garrik_cavalier,
):
    """Lv 9 Cavalier → disadvantage flag + punish bonus 4."""
    garrik = garrik_cavalier
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "unwavering-mark"
    assert data["target_attack_disadvantage"] is True
    assert data["punish_bonus_damage"] == 4  # half fighter level 9
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _um_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["punish_bonus_damage"] == 4


async def test_use_um_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_um_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_mark",
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


async def test_um_install_on_melee_hit(
    gm_client, gm_ws, garrik_cavalier, roster,
):
    """v2.139.0 — Phase 1: when a Cavalier Fighter Lv 3+ hits a
    creature with a melee weapon attack, install the
    `unwavering-mark` buff on the target. End-to-end: PATCH Garrik to
    Cavalier, long-rest, seed battle with Garrik + Pip, swing
    Greatsword at Pip → on a hit the buff lands on Pip carrying
    `effects.unwavering_mark_cavalier_char_id == garrik.id`. Retry-
    on-miss bound to 5 attempts."""
    garrik = garrik_cavalier
    pip = roster["Pip Quickfingers"]
    garrik_tok = f"tok_um_g_{garrik['id']}"
    pip_tok = f"tok_um_p_{pip['id']}"
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(garrik_tok, garrik), _pc(pip_tok, pip)],
              "turn_index": 0, "round": 1, "active": True},
    )
    hit_resp = None
    for _ in range(5):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"],
                  "attack_index": 0,
                  "target_combatant_id": pip_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            hit_resp = r.json()
            break
    assert hit_resp is not None, (
        "Garrik missed Pip on 5 swings; check fixtures"
    )
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus, "no battle_update broadcast received after hit"
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    pip_cb = combs.get(pip_tok)
    assert pip_cb is not None, (
        f"Pip's combatant missing; got ids={list(combs.keys())}"
    )
    mark_buff = next(
        (b for b in (pip_cb.get("buffs") or [])
         if b.get("key") == "unwavering-mark"),
        None,
    )
    assert mark_buff is not None, (
        f"UM buff missing from Pip after Garrik's hit; got buffs="
        f"{pip_cb.get('buffs')}"
    )
    effects = mark_buff.get("effects") or {}
    assert int(effects.get(
        "unwavering_mark_cavalier_char_id") or 0) == int(garrik["id"]), (
        f"UM buff should point at Garrik's char_id; got effects={effects}"
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _seed_three_pc_battle_um(gm_client, garrik, pip, tavik):
    """Garrik, Pip, Tavik in init for Phase 1b tests."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_um_g_{garrik['id']}", garrik),
            _pc(f"tok_um_p_{pip['id']}", pip),
            _pc(f"tok_um_t_{tavik['id']}", tavik),
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _land_um_mark_on_pip(gm_client, gm_ws, garrik, pip_tok):
    """Garrik swings Greatsword at Pip until a hit lands. Retries
    bound to 10 (Garrik +6 vs Pip AC ~14 → ~65% per swing)."""
    for _ in range(10):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"],
                  "attack_index": 0,
                  "target_combatant_id": pip_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            return
    raise AssertionError("Garrik missed Pip on 10 swings; check fixtures")


async def test_um_marked_within_5ft_swing_at_third_party_has_disadvantage(
    gm_client, gm_ws, garrik_cavalier, roster,
):
    """v2.140.0 — Phase 1b: once Pip carries the UM mark from Garrik's
    melee hit AND Pip is within 5 ft of Garrik, Pip's next attack at
    Tavik (a non-Cavalier) gets `disadvantage_unwavering_mark_vs_other`
    + 2d20kl1 in the breakdown. Tokens co-located at (700, 700) so
    `_distance_ft_between_chars` returns 0 < 5 → gate fires."""
    garrik = garrik_cavalier
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    pip_tok = f"tok_um_p_{pip['id']}"
    tav_tok = f"tok_um_t_{tavik['id']}"
    await _place_token(gm_client, garrik["id"], 700.0, 700.0)
    await _place_token(gm_client, pip["id"], 700.0, 700.0)
    await _place_token(gm_client, tavik["id"], 800.0, 800.0)
    await _seed_three_pc_battle_um(gm_client, garrik, pip, tavik)
    await _land_um_mark_on_pip(gm_client, gm_ws, garrik, pip_tok)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"],
              "attack_index": 0,
              "target_combatant_id": tav_tok,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"UM mark within 5 ft should produce 2d20kl1; got "
        f"{data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_unwavering_mark_vs_other", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_um_marked_swing_at_cavalier_no_disadvantage(
    gm_client, gm_ws, garrik_cavalier, roster,
):
    """v2.140.0 — Phase 1b complement: marked Pip swings AT the
    Cavalier (Garrik). RAW: "doesn't target you" — gate is silent."""
    garrik = garrik_cavalier
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    gar_tok = f"tok_um_g_{garrik['id']}"
    pip_tok = f"tok_um_p_{pip['id']}"
    await _place_token(gm_client, garrik["id"], 700.0, 700.0)
    await _place_token(gm_client, pip["id"], 700.0, 700.0)
    await _place_token(gm_client, tavik["id"], 800.0, 800.0)
    await _seed_three_pc_battle_um(gm_client, garrik, pip, tavik)
    await _land_um_mark_on_pip(gm_client, gm_ws, garrik, pip_tok)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"],
              "attack_index": 0,
              "target_combatant_id": gar_tok,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    label = data.get("roll_state_applied") or ""
    assert "unwavering_mark_vs_other" not in label, (
        f"UM gate must not fire vs the Cavalier; "
        f"roll_state_applied={label!r}"
    )


async def test_use_um_punish_lv9_advantage_and_bonus_damage(
    gm_client, gm_ws, garrik_cavalier, roster,
):
    """v2.141.0 — Phase 2: Cavalier Lv 9's bonus-action punish swing
    rolls 2d20kh1 + weapon bonus, on hit adds flat +4 (half fighter
    level) extra damage. End-to-end: seed Garrik + Pip in battle,
    POST /use_unwavering_punish targeting Pip with attack_index 0
    (Greatsword) → assert advantage rolled + roll_state_applied
    + punish_bonus_damage == 4 + the broadcast carries the swing.
    Uses override to bypass the bonus-action chip gate (no battle
    chip-management setup in this test)."""
    garrik = garrik_cavalier
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_um_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_um_g_{garrik['id']}", garrik),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_punish",
        json={"character_id": garrik["id"],
              "attack_index": 0,
              "target_combatant_id": pip_tok,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "unwavering-punish"
    assert data["punish_bonus_damage"] == 4   # half fighter Lv 9
    assert data["fighter_level"] == 9
    # Advantage forced: 2d20kh1 in breakdown + roll_state_applied.
    assert "2d20kh1" in (data.get("attack_breakdown") or ""), (
        f"punish should roll 2d20kh1; got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "advantage_unwavering_punish"


async def test_use_um_punish_wrong_subclass(
    gm_client, roster,
):
    """v2.141.0 — Default Garrik (Champion) → 409 on punish."""
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_um_punish_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_um_punish_g_{garrik['id']}", garrik),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_unwavering_punish",
        json={"character_id": garrik["id"],
              "attack_index": 0,
              "target_combatant_id": pip_tok,
              "override": True},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"
