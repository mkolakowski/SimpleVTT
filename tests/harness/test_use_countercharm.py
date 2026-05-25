"""v2.54.0 — Bard Countercharm (Lv 6+) ally aura vs charmed/frightened.

The first condition-gated save aura — Countercharm only fires when
the spell would install charmed or frightened (per
`_SPELL_CONDITION_MAP[slug].key`), not on every save. Allies (any
PC in init under v1 simplification) get advantage on their save d20.

Flow:
  - Lyra (Bard Lv 6) POSTs `/use_countercharm` → `countercharm-active`
    self-buff installed on her combatant; action chip flipped.
  - Anyone in init who's then targeted by a save-vs-charm/frighten
    spell rolls 2d20kh1 instead of 1d20 (server-side base_expression
    swap in the cast_spell PC save roll_request).
  - Broadcast: `feature_used(source="countercharm")` names the bard.

Tests:
  - happy path: Lyra → /use_countercharm → buff installed; Lyra
    casts Suggestion at Krieger (in init) → roll_request
    base_expression="2d20kh1" + Countercharm broadcast.
  - control (no buff): Lyra skips /use_countercharm; casts
    Suggestion at Krieger → base_expression="1d20"; no broadcast.
  - control (wrong condition): Lyra uses Countercharm but casts
    Hold Person (Paralyzed, not Charmed/Frightened) at Krieger →
    base_expression="1d20" + no Countercharm broadcast (gate fired
    on spell-condition, not on save_ability).
  - endpoint validation: wrong class (Pip → 409 wrong_class).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra's spell list ordering — see app/demo_seed.py::_bard_sheet.
# 0 Vicious Mockery, 1 Mage Hand, 2 Minor Illusion, 3 Prestidigitation,
# 4 Healing Word, 5 Cure Wounds, 6 Faerie Fire, 7 Heroism,
# 8 Thunderwave, 9 Suggestion, 10 Invisibility, 11 Hold Person, ...
SUGGESTION_INDEX = 9
HOLD_PERSON_LYRA_INDEX = 11


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_cc_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _countercharm_broadcasts(gm_ws, bard_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "countercharm"
        and (m.get("data") or {}).get("character_id") == bard_char_id
    ]


async def _wait_for_roll_request(gm_ws):
    """Block-with-timeout until a roll_request broadcast lands. The
    cast_spell flow emits this async, so the test post() can return
    before the WS message arrives — `buffered()` reads can race the
    broadcast. `wait_for` resolves that race.
    """
    return await gm_ws.wait_for("roll_request", timeout=3.0)


async def test_use_countercharm_installs_buff(gm_client, gm_ws, roster, lyra_rested):
    """POST /use_countercharm → 200 + buff installed on Lyra's
    combatant + action chip flipped + feature_used broadcast."""
    lyra = lyra_rested
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=10),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_countercharm",
        json={"character_id": lyra["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 1
    assert data["buff_installed"] is True
    # feature_used broadcast (from the endpoint itself, not the
    # save-roll trigger — different source-of-truth).
    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "countercharm"
    assert msg["data"]["character_id"] == lyra["id"]


async def test_countercharm_grants_advantage_on_charm_save(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Lyra uses Countercharm, then casts Suggestion at Krieger →
    Krieger's save roll_request carries base_expression="2d20kh1"
    AND a feature_used(source=countercharm) broadcast fires naming
    Lyra.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=10),
        _make_combatant(krieger["name"], krieger["id"], init=8),
    ])
    # Step 1: activate Countercharm.
    activate = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_countercharm",
        json={"character_id": lyra["id"], "override": True},
    )
    assert activate.status_code == 200, activate.text

    gm_ws.mark()
    # Step 2: Cast Suggestion at Krieger. Suggestion is Wis save,
    # installs Charmed via the v2.54.0 _SPELL_CONDITION_MAP entry.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_cc_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"
    assert data["auto_save_target_kind"] == "pc"
    assert data["auto_save_prompted"] is True

    rr = await _wait_for_roll_request(gm_ws)
    assert rr is not None, "expected a roll_request broadcast for Krieger"
    # Krieger has Danger Sense (Dex-only) so it won't add kh1 here.
    # Caelan is NOT in this battle so no Aura of Protection bonus.
    # So the only modifier should be the Countercharm kh1 swap.
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Countercharm should swap d20 → 2d20kh1 on Wis save vs Suggestion; "
        f"got {rr['data']['base_expression']!r}"
    )
    cc_msgs = _countercharm_broadcasts(gm_ws, lyra["id"])
    assert cc_msgs, (
        f"expected feature_used(source=countercharm) for Lyra; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_countercharm_skips_without_active_buff(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Control: Lyra does NOT activate Countercharm. Casting
    Suggestion at Krieger uses the standard base_expression="1d20";
    no Countercharm broadcast.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=10),
        _make_combatant(krieger["name"], krieger["id"], init=8),
    ])

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_cc_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = await _wait_for_roll_request(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"without Countercharm active, base_expression should be 1d20; "
        f"got {rr['data']['base_expression']!r}"
    )
    cc_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "countercharm"
    ]
    assert not cc_msgs, (
        f"no Countercharm broadcast should fire when the buff isn't active: {cc_msgs}"
    )


async def test_countercharm_skips_wrong_condition_spell(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Lyra DOES use Countercharm, but casts Hold Person (installs
    Paralyzed, NOT Charmed/Frightened). The Countercharm gate is
    condition-keyed, not save-ability-keyed, so Krieger's save
    base_expression stays "1d20" + no Countercharm broadcast.
    """
    lyra = lyra_rested
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=10),
        _make_combatant(krieger["name"], krieger["id"], init=8),
    ])
    # Activate Countercharm — buff installed; condition-gate
    # SHOULD NOT fire on Hold Person.
    activate = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_countercharm",
        json={"character_id": lyra["id"], "override": True},
    )
    assert activate.status_code == 200, activate.text

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": HOLD_PERSON_LYRA_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_cc_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = await _wait_for_roll_request(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Hold Person installs Paralyzed (not Charmed/Frightened); "
        f"Countercharm should NOT fire — base_expression should be 1d20; "
        f"got {rr['data']['base_expression']!r}"
    )
    cc_msgs = _countercharm_broadcasts(gm_ws, lyra["id"])
    assert not cc_msgs, (
        f"Countercharm broadcast should NOT fire for non-charmed/frightened "
        f"spell: {cc_msgs}"
    )


async def test_use_countercharm_wrong_class(gm_client, roster):
    """Pip (Rogue) → 409 wrong_class."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_countercharm",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "wrong_class"
    assert data["expected"] == "bard"
