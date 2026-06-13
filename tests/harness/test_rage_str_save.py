"""v2.99.26 — Rage advantage on STR saves.

RAW (PHB p.48, Barbarian Lv 1 Rage): while raging, "you have
advantage on Strength checks and Strength saving throws." The rage
buff has carried `effects.advantage_on = ["str_check", "str_save",
"str_attack"]` since v2.20.0. The `str_attack` half is consumed
by `_attacker_has_str_attack_advantage` (v2.49.238). v2.99.26
wires the `str_save` half via the new helper
`_pc_has_rage_str_save_advantage` consuming the same buff marker.

The save-roll construction hook fires in all 3 sites:
  - `/cast_spell` single-target PC save (roll_request)
  - `/cast_spell` AoE PC save (roll_request)
  - `/place_aoe` PC server-rolled save (direct expression)

Krieger Stonefist is the demo fixture (Half-Orc Berserker Lv 7).
Thalindra Moonwhisper now carries Gust of Wind (Wizard L2, STR
save) as the test trigger spell — appended to her spell list in
v2.99.26.

Tests:
  - happy: Krieger rages → Thalindra casts Gust of Wind at him →
    base_expression="2d20kh1" + feature_used(source=rage-str-save)
    broadcast fires.
  - control non-raging: Krieger doesn't rage → same cast → no swap.
  - control non-STR save: Krieger rages → Thalindra casts Fireball
    (DEX save) → no swap (only STR saves get the advantage).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _spell_index(gm_client, char_id, name):
    """Resolve a spell's index in the sheet's spell list by name — robust to
    demo-seed spell-list reordering (hardcoded indices drift as spells are
    added). Gust of Wind is Thalindra's STR-save trigger; Banishment is the
    CHA-save control (Krieger has no CHA-save advantage to confound it)."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    for i, sp in enumerate(sheet.get("spells") or []):
        nm = sp.get("name") if isinstance(sp, dict) else sp
        if str(nm).strip().lower() == name.strip().lower():
            return i
    return -1


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_rss_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 60,
        "hp_max": 60,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _race_or_rage_broadcasts(gm_ws, character_id: int, source: str) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == source
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def test_rage_grants_advantage_on_str_save(
    gm_client, gm_ws, thalindra_rested, krieger_rested,
):
    """Krieger activates Rage; Thalindra casts Gust of Wind at him →
    base_expression="2d20kh1" AND feature_used(source=rage-str-save)
    broadcast fires for Krieger.
    """
    thal = thalindra_rested
    krieger = krieger_rested
    gust_index = await _spell_index(gm_client, thal["id"], "Gust of Wind")
    assert gust_index >= 0, "Thalindra must know Gust of Wind"
    await _seed_battle(gm_client, [_tok(thal), _tok(krieger)])
    # Activate Rage on Krieger.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    # Thalindra casts Gust of Wind at Krieger.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": gust_index,
            "slot_level": 2,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_rss_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "STR"
    assert data["auto_save_target_kind"] == "pc"

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None, "expected roll_request broadcast for Krieger's STR save"
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Rage should set base_expression to 2d20kh1 on STR save; "
        f"got {rr['data']['base_expression']!r}"
    )
    msgs = _race_or_rage_broadcasts(gm_ws, krieger["id"], "rage-str-save")
    assert msgs, (
        f"expected feature_used(source=rage-str-save) for Krieger; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_rage_skips_str_save_when_not_raging(
    gm_client, gm_ws, thalindra_rested, krieger_rested,
):
    """Control: Krieger is NOT raging → Gust of Wind STR save rolls
    plain 1d20; no rage-str-save broadcast.
    """
    thal = thalindra_rested
    krieger = krieger_rested
    gust_index = await _spell_index(gm_client, thal["id"], "Gust of Wind")
    assert gust_index >= 0, "Thalindra must know Gust of Wind"
    await _seed_battle(gm_client, [_tok(thal), _tok(krieger)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": gust_index,
            "slot_level": 2,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_rss_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"non-raging Krieger should NOT have advantage; got "
        f"base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_or_rage_broadcasts(gm_ws, krieger["id"], "rage-str-save")
    assert not msgs


async def test_rage_skips_non_str_save_when_raging(
    gm_client, gm_ws, thalindra_rested, krieger_rested,
):
    """Control: Krieger rages then Thalindra casts Banishment (CHA
    save) → no STR-save advantage. Confirms the rage advantage gates
    on STR saves only — DEX/CON/etc. saves remain plain 1d20.

    Note: DEX save would trigger Danger Sense's Lv 2 advantage and
    confound the test. CHA save has no overlap with Krieger's other
    advantage sources.
    """
    thal = thalindra_rested
    krieger = krieger_rested
    banishment_index = await _spell_index(gm_client, thal["id"], "Banishment")
    assert banishment_index >= 0, "Thalindra must know Banishment"
    await _seed_battle(gm_client, [_tok(thal), _tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": banishment_index,
            "slot_level": 4,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_rss_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "CHA"

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Rage should NOT grant advantage on CHA save; got "
        f"base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_or_rage_broadcasts(gm_ws, krieger["id"], "rage-str-save")
    assert not msgs, (
        f"rage-str-save broadcast should NOT fire on CHA save: {msgs}"
    )
