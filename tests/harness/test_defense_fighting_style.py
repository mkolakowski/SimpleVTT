"""v2.99.95 — Defense Fighting Style auto-AC engine.

RAW (PHB p.72-91): Defense Fighting Style — "While you are wearing
armor, you gain a +1 bonus to AC." v2.99.95 wires this into
``_read_target_ac`` (the function /attack uses for hit determination)
so a PC with fighting_style="defense" + equipped armor shows
target_ac = base + 1.

Two gates:
  1. ``sheet.fighting_style == "defense"``
  2. an inventory entry with ``type == "armor"`` and ``equipped: True``

Unarmored Defense builds (Monk, Barbarian) fail gate 2 even though
their AC is high — Defense by RAW requires actually wearing armor.

No demo PC has Defense by default; tests PATCH Garrik
(Fighter Lv 6, chain mail equipped, AC 18) to "defense" and verify
the AC computation. Garrik's stock fighting_style is "great_weapon"
(restored in teardown).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _attack_for_target_ac(gm_client, attacker_id, target_combatant_id):
    """Fire an /attack call against the target — the response's
    ``target_ac`` field is what we assert on. Hit/miss outcome
    doesn't matter for this test; we just need the AC the server
    computed at hit-determination time.
    """
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker_id,
            "attack_index": 0,
            "target_combatant_id": target_combatant_id,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("target_ac")


@pytest_asyncio.fixture
async def garrik_defense_setup(gm_client, roster):
    """PATCH Garrik to fighting_style="defense"; restore
    "great_weapon" in teardown. Yields (garrik, tavik) for the
    attack setup.
    """
    garrik = roster["Garrik Ironside"]
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"fighting_style": "defense"},
    )
    yield garrik, tavik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"fighting_style": "great_weapon"},
    )


async def test_defense_adds_one_to_ac_when_wearing_armor(
    gm_client, garrik_defense_setup,
):
    """Garrik wears chain mail (sheet says equipped: True) and now
    has fighting_style="defense". target_ac should be 19 (base 18
    + Defense +1).
    """
    garrik, tavik = garrik_defense_setup
    garrik_tok = f"tok_def_{garrik['id']}"
    tavik_tok = f"tok_def_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
        _mkc(garrik_tok, garrik["id"], name=garrik["name"]),
    ])
    target_ac = await _attack_for_target_ac(gm_client, tavik["id"], garrik_tok)
    assert target_ac == 19, (
        f"Defense should add +1 to Garrik's AC 18 → expected 19; "
        f"got {target_ac!r}"
    )


async def test_no_defense_no_bonus(gm_client, roster):
    """Control: Garrik's stock fighting_style is "great_weapon".
    target_ac should be exactly 18 (sheet value, no +1).
    """
    garrik = roster["Garrik Ironside"]
    tavik = roster["Brother Tavik Stonebrow"]
    garrik_tok = f"tok_def_ctl_{garrik['id']}"
    tavik_tok = f"tok_def_ctl_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
        _mkc(garrik_tok, garrik["id"], name=garrik["name"]),
    ])
    target_ac = await _attack_for_target_ac(gm_client, tavik["id"], garrik_tok)
    assert target_ac == 18, (
        f"Without Defense style, Garrik's AC should be base 18; "
        f"got {target_ac!r}"
    )


async def test_defense_no_bonus_without_armor(gm_client, roster):
    """Kael (Monk, Unarmored Defense) has no equipped armor item.
    PATCH him to fighting_style="defense" — the +1 should NOT
    apply because RAW gates on "wearing armor". Kael's sheet AC
    is 16 (Unarmored Defense); we expect 16, not 17.
    """
    kael = roster["Kael Brightleaf"]
    tavik = roster["Brother Tavik Stonebrow"]
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"fighting_style": "defense"},
        )
        kael_tok = f"tok_def_kael_{kael['id']}"
        tavik_tok = f"tok_def_kael_{tavik['id']}"
        await _seed_battle(gm_client, [
            _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
            _mkc(kael_tok, kael["id"], name=kael["name"]),
        ])
        target_ac = await _attack_for_target_ac(
            gm_client, tavik["id"], kael_tok,
        )
        assert target_ac == 16, (
            f"Defense requires worn armor (Kael is unarmored); "
            f"expected AC 16, got {target_ac!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"fighting_style": ""},
        )
