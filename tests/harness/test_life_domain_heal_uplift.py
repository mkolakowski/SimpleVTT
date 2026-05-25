"""v2.58.0 — Life Domain Cleric heal-spell uplift hook.

Two stacked features on outgoing heals from a Life Domain Cleric:

  - **Disciple of Life** (Lv 1+) adds `2 + spell_level` HP to the
    target heal. Applies to ANY target including self.
  - **Blessed Healer** (Lv 6+) ALSO heals the caster for `2 +
    spell_level` when the target is NOT the caster.

Wired in `app/routes/tabletop_routes.py` via the
`_life_domain_heal_uplift(caster_sheet, slot_level, target_is_self)`
helper called in the /cast_spell heal-resolution branch. The
target uplift is composed into `heal_rolled_with_uplift` before
the single `_apply_heal_to_combatant` call; the self-heal is a
separate call against the caster's own combatant. Two
`feature_used` broadcasts (`source=disciple-of-life`,
`source=blessed-healer`) credit the chat card.

Tests:
  - Tavik (Cleric Lv 6 Life Domain) casts Cure Wounds at Krieger
    (Barbarian, not the caster) → target uplifted by +3 (slot
    Lv 1 + 2), caster gets +3 self-heal via Blessed Healer; both
    broadcasts fire.
  - Tavik casts Healing Word on himself (target IS caster) →
    Disciple of Life applies (+3), Blessed Healer does NOT
    (target IS caster); only the Disciple broadcast fires.
  - Lyra (Bard, not Life Domain) casts Cure Wounds at Krieger →
    no uplift, no broadcasts (control).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Tavik's spell list — Cure Wounds at index 4, Healing Word at index 5
# (from `_cleric_sheet` order: cantrips × 3, then Bless, Cure Wounds,
# Healing Word, ...).
TAVIK_CURE_WOUNDS_INDEX = 4
TAVIK_HEALING_WORD_INDEX = 5
# Lyra's spell list — Cure Wounds at index 2 (Lyra's known/cantrips
# vary by version; will resolve from her sheet below).


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


@pytest_asyncio.fixture
async def krieger_wounded(gm_client, roster):
    """Long-rest Krieger then damage him 30 HP so heals have room
    to land (caps at hp_max otherwise)."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    # Damage to 40 HP (max 75 → 40).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"hp": {"current": 40}},
    )
    return krieger


def _make_combatant(name, char_id, hp_current=40, hp_max=75, init=10):
    return {
        "id": f"tok_life_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _broadcasts_for_source(gm_ws, source: str, char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == source
        and (m.get("data") or {}).get("character_id") == char_id
    ]


async def test_disciple_and_blessed_healer_on_other_target(
    gm_client, gm_ws, tavik_rested, krieger_wounded,
):
    """Tavik casts Cure Wounds (L1 slot) at Krieger.
    Disciple of Life uplifts Krieger by +3 (2 + L1);
    Blessed Healer self-heals Tavik for +3 (target is not caster);
    both broadcasts fire.
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    # Tavik full HP 51; damage to 45 so Blessed Healer has room.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 45}},
    )
    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"],
                        hp_current=45, hp_max=51),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=40, hp_max=75),
    ])
    gm_ws.mark()

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_CURE_WOUNDS_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_combatant_id": f"tok_life_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    data = cast_resp.json()
    # Uplifts surface on the cast response via the broadcast payload —
    # check the WS broadcasts instead of the JSON body (the body
    # carries the spell-cast event, not the feature_used events).
    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", tavik["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", tavik["id"])
    assert dol_msgs, (
        f"expected disciple-of-life broadcast; buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    assert bh_msgs, (
        f"expected blessed-healer broadcast (target ≠ caster); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    # Disciple of Life: 2 + 1 = +3 in the broadcast feature_name.
    assert "+3" in (dol_msgs[0].get("data") or {}).get("feature_name", ""), (
        f"disciple-of-life broadcast should show +3 uplift; got "
        f"{(dol_msgs[0].get('data') or {}).get('feature_name')!r}"
    )
    # Blessed Healer: +3 to Tavik.
    assert "+3" in (bh_msgs[0].get("data") or {}).get("feature_name", ""), (
        f"blessed-healer broadcast should show +3 self-heal; got "
        f"{(bh_msgs[0].get('data') or {}).get('feature_name')!r}"
    )


async def test_blessed_healer_skips_self_target(
    gm_client, gm_ws, tavik_rested,
):
    """Tavik casts Healing Word at himself. Disciple of Life applies
    (target IS a creature, even if it's the caster); Blessed Healer
    does NOT (RAW: "creature OTHER than you").
    """
    tavik = tavik_rested
    # Damage Tavik down so heals land.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 30}},
    )
    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"],
                        hp_current=30, hp_max=51),
    ])
    gm_ws.mark()

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_combatant_id": f"tok_life_{tavik['id']}",
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", tavik["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", tavik["id"])
    assert dol_msgs, "expected disciple-of-life broadcast on self-heal"
    assert not bh_msgs, (
        f"blessed-healer should NOT fire on self-heal; got: "
        f"{[(m.get('data') or {}).get('feature_name') for m in bh_msgs]}"
    )


async def test_no_uplift_for_non_life_domain_caster(
    gm_client, gm_ws, lyra_rested, krieger_wounded,
):
    """Control: Lyra (College of Lore Bard) casts Cure Wounds at
    Krieger → no Disciple of Life uplift, no Blessed Healer self-
    heal, no broadcasts.
    """
    lyra = lyra_rested
    krieger = krieger_wounded
    # Lyra's spell list (from `_bard_sheet`): index 5 is Cure Wounds
    # (0=Vicious Mockery, 1=Mage Hand, 2=Minor Illusion,
    # 3=Prestidigitation, 4=Healing Word, 5=Cure Wounds).
    LYRA_CURE_WOUNDS_INDEX = 5

    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"],
                        hp_current=30, hp_max=40),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=40, hp_max=75),
    ])
    gm_ws.mark()

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": LYRA_CURE_WOUNDS_INDEX,
            "slot_level": 1,
            "class_slug": "bard",
            "target_combatant_id": f"tok_life_{krieger['id']}",
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", lyra["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", lyra["id"])
    assert not dol_msgs, (
        f"non-Life-Domain caster should NOT fire disciple-of-life: "
        f"{[(m.get('data') or {}).get('feature_name') for m in dol_msgs]}"
    )
    assert not bh_msgs, (
        f"non-Life-Domain caster should NOT fire blessed-healer: "
        f"{[(m.get('data') or {}).get('feature_name') for m in bh_msgs]}"
    )
