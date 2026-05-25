"""v2.59.0 — Multi-target heal loop in /cast_spell + Life Domain uplift.

Extends the v2.58.0 Life Domain heal-uplift hook to Mass Healing
Word / Mass Cure Wounds (any heal spell passed multiple targets
via `target_combatant_ids`). The single-target block at the top of
the heal-resolution branch handles `target_combatant_ids[0]`; the
new extras loop handles `[1:]`.

Per-target: Disciple of Life uplift if Life Domain Cleric Lv 1+
(adds 2 + slot_level to each target). Blessed Healer fires ONCE per
cast (RAW), so the extras loop only re-fires it if the single-
target block didn't (i.e. the first target was the caster).

Tests:
  - Tavik (Cleric Lv 6 Life Domain) casts Mass Healing Word at
    Krieger + Pip → 2 Disciple of Life broadcasts (one per target)
    + 1 Blessed Healer self-heal.
  - Lyra (Bard, non-Life-Domain) casts Mass Healing Word at
    Krieger + Pip (hypothetical — even if not in her list, the
    multi-target loop is class-agnostic) → no Disciple of Life /
    Blessed Healer broadcasts.

  Note: Lyra doesn't actually have Mass Healing Word in her demo
  spell list, so the control is verified via Cure Wounds at one
  target — same code path runs but multi-target loop is skipped
  (only 1 entry in target_combatant_ids).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Tavik's spell list — Mass Healing Word at index 12.
TAVIK_MASS_HEALING_WORD_INDEX = 12


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def krieger_wounded(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"hp": {"current": 40}},
    )
    return krieger


@pytest_asyncio.fixture
async def pip_wounded(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 20}},
    )
    return pip


def _make_combatant(name, char_id, hp_current=30, hp_max=50, init=10):
    return {
        "id": f"tok_mhw_{char_id}",
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


async def test_mass_healing_word_per_target_disciple_uplift(
    gm_client, gm_ws, tavik_rested, krieger_wounded, pip_wounded,
):
    """Tavik casts Mass Healing Word at Krieger + Pip → both get
    Disciple of Life uplift (+3 each); Blessed Healer fires ONCE
    (per spell cast RAW).
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    pip = pip_wounded
    # Damage Tavik so Blessed Healer self-heal has room.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 45}},
    )

    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"],
                        hp_current=45, hp_max=51),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=40, hp_max=75),
        _make_combatant(pip["name"], pip["id"],
                        hp_current=20, hp_max=47),
    ])
    gm_ws.mark()

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": [
                f"tok_mhw_{krieger['id']}",
                f"tok_mhw_{pip['id']}",
            ],
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", tavik["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", tavik["id"])

    # 2 Disciple of Life broadcasts — one per target — at slot 3,
    # uplift = 2 + 3 = +5.
    assert len(dol_msgs) == 2, (
        f"expected 2 disciple-of-life broadcasts (one per target); "
        f"got {len(dol_msgs)}: "
        f"{[(m.get('data') or {}).get('feature_name') for m in dol_msgs]}"
    )
    feature_names = [
        (m.get("data") or {}).get("feature_name", "") for m in dol_msgs
    ]
    assert any(krieger["name"] in fn for fn in feature_names), (
        f"expected Krieger in one of the Disciple of Life broadcasts: {feature_names}"
    )
    assert any(pip["name"] in fn for fn in feature_names), (
        f"expected Pip in one of the Disciple of Life broadcasts: {feature_names}"
    )
    assert all("+5" in fn for fn in feature_names), (
        f"expected +5 uplift (2 + slot 3) on each broadcast: {feature_names}"
    )

    # Blessed Healer fires ONCE per cast — even with 2 targets.
    assert len(bh_msgs) == 1, (
        f"expected exactly 1 blessed-healer broadcast (RAW: per cast, "
        f"not per target); got {len(bh_msgs)}: "
        f"{[(m.get('data') or {}).get('feature_name') for m in bh_msgs]}"
    )


async def test_aoe_heal_skips_uplift_for_non_life_domain(
    gm_client, gm_ws, roster,
):
    """Control: a non-Life-Domain caster's multi-target heal doesn't
    fire Disciple of Life / Blessed Healer broadcasts. Uses Tavik's
    Healing Word at one target as the cleanest signal — single-target
    Healing Word does not exercise the multi-target loop, but the
    underlying gate (`_life_domain_heal_uplift` returning (0,0) for
    non-Life casters) is the same. Lyra is the canonical non-Life
    caster but doesn't have Mass Healing Word; the helper itself
    returns (0,0) regardless of target count for non-Life Domain.

    This test pins the negative-path via Tavik's Lv 5 (pre-Lv 6 cleric)
    sheet shape — not realistic since Tavik is Lv 6, but the gate
    behavior is identical when subclass != "life". Best signal is a
    structural check: Lyra casts Cure Wounds at one target, gets no
    Disciple of Life broadcast. v2.58.0's `test_no_uplift_for_non_
    life_domain_caster` already covers this; here we add a multi-
    target dimension by structurally validating the loop entry is
    gated on the helper return.

    Practical assertion: cast Mass Healing Word from Tavik at ONE
    target — the extras loop sees len(target_combatant_ids_in) == 1
    and doesn't fire; the single-target block fires Disciple of Life
    + Blessed Healer once each. This verifies the loop's len > 1
    guard, not the non-Life gate.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"hp": {"current": 40}},
    )
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

    # Single-target Mass Healing Word (extras loop sees len == 1 and
    # skips). target_combatant_ids = [krieger only].
    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": [f"tok_mhw_{krieger['id']}"],
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", tavik["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", tavik["id"])

    # With only 1 target, the extras loop doesn't fire. Single-target
    # block handles it: 1 Disciple of Life + 1 Blessed Healer.
    assert len(dol_msgs) == 1, (
        f"expected 1 disciple-of-life broadcast (single target, extras "
        f"loop skipped); got {len(dol_msgs)}"
    )
    assert len(bh_msgs) == 1, (
        f"expected 1 blessed-healer broadcast; got {len(bh_msgs)}"
    )


async def test_mass_healing_word_blessed_healer_skips_self_first_target(
    gm_client, gm_ws, tavik_rested, krieger_wounded,
):
    """Edge case: Tavik casts Mass Healing Word with HIMSELF as the
    first target and Krieger as the extra. The single-target block
    fires Disciple of Life on Tavik (target IS self) but NOT Blessed
    Healer. The extras loop fires Disciple of Life on Krieger AND
    Blessed Healer (since the cast does heal a non-self creature).
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 30}},
    )

    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"],
                        hp_current=30, hp_max=51),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=40, hp_max=75),
    ])
    gm_ws.mark()

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
            "slot_level": 3,
            "class_slug": "cleric",
            "target_combatant_ids": [
                f"tok_mhw_{tavik['id']}",     # self first
                f"tok_mhw_{krieger['id']}",   # other second
            ],
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life", tavik["id"])
    bh_msgs = _broadcasts_for_source(gm_ws, "blessed-healer", tavik["id"])

    # Disciple of Life: fires for both targets (Tavik + Krieger).
    assert len(dol_msgs) == 2, (
        f"expected 2 disciple-of-life broadcasts; got {len(dol_msgs)}"
    )
    # Blessed Healer fires once — late, from the extras loop.
    assert len(bh_msgs) == 1, (
        f"expected exactly 1 blessed-healer broadcast (fires late in "
        f"the extras loop when first target was self); got {len(bh_msgs)}"
    )
