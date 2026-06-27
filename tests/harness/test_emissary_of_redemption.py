"""v2.99.292 — Redemption Paladin: Emissary of Redemption (H.2 deeper, Lv 20).

H.2 Lv 20 Redemption ship. CLOSES the H.2 Lv 20 batch (5/5
oaths). RAW XGE p.39: passive permanent capstone. Resistance
to all damage from creatures + half-damage radiant counter on
hit. Both negated against a creature you attack/spell/damage
until next long rest.

**v2.700.0 (Phase 8):** both halves are mechanical. The endpoint
installs a permanent `emissary-of-redemption` buff with
`effects.resistance_to: ["all"]` (the damage pipeline halves every
type against the wildcard), and the radiant-reflect fires from the
on-damage-taken hook (Redemption Lv 20 gate) — a creature that hits
the Paladin takes radiant = half the damage taken. The per-target
"until you attack them" caveat stays GM-narrated. No chip cost.

Tests:
  - Lv 20 happy → resistance_all_creature_damage True,
    radiant_back_fraction 0.5, resistance_installed True.
  - Reflect: a PC attacker that hits the Lv 20 Paladin → an
    `emissary-of-redemption` broadcast with radiant_damage ≥ 1.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, c, hp=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "", "font_override": "",
        "default_encounter_id": "", "hp_threshold_1": "", "hp_threshold_2": "",
        "hp_threshold_3": "", "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _er_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "emissary-of-redemption"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_redemption_lv20(gm_client, roster):
    """PATCH Caelan to Redemption Lv 20."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 20},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_er_happy_lv20(
    gm_client, gm_ws, caelan_redemption_lv20,
):
    """Lv 20 Redemption → resistance + half radiant back."""
    caelan = caelan_redemption_lv20
    # Seed a battle so `_install_buff` (resistance-to-all) lands.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(f"tok_er_{caelan['id']}", caelan, hp=60)],
              "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resistance_all_creature_damage"] is True
    assert data["radiant_back_fraction"] == 0.5
    assert data["paladin_level"] == 20
    assert data["resistance_installed"] is True
    await asyncio.sleep(0.3)
    feats = _er_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_er_reflects_radiant_on_attack(
    gm_client, gm_ws, caelan_redemption_lv20, roster, auto_apply_on,
):
    """v2.700.0 — radiant-reflect on-damage hook. A PC attacker (Pip) that
    hits the Lv 20 Redemption Paladin triggers an `emissary-of-redemption`
    broadcast with radiant_damage = half the damage Caelan took. Mirrors the
    Scornful Rebuke auto-hook test; retry-on-miss bound to 10."""
    caelan = caelan_redemption_lv20
    pip = roster["Pip Quickfingers"]
    cael_tok = f"tok_er_c_{caelan['id']}"
    pip_tok = f"tok_er_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(cael_tok, caelan, hp=80),
                             _pc(pip_tok, pip)],
              "turn_index": 1, "round": 1, "active": True},
    )
    fired = False
    for _ in range(10):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"], "attack_index": 0,
                  "target_combatant_id": cael_tok, "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is not True:
            continue
        await asyncio.sleep(0.3)
        feats = _er_broadcasts(gm_ws, caelan["id"])
        if feats:
            fired = True
            d = feats[-1]["data"]
            assert d["radiant_damage"] >= 1, d
            assert int(d.get("attacker_char_id") or 0) == int(pip["id"]), d
            break
    assert fired, "Emissary of Redemption radiant-reflect didn't fire on a hit"


async def test_use_er_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_er_level_gate(
    gm_client, roster,
):
    """Redemption Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Redemption", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_emissary_of_redemption",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )
