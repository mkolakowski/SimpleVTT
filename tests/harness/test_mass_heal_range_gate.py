"""v2.61.1 — F1 range gate in the v2.59.0 AoE heal extras loop.

Mass Healing Word + Mass Cure Wounds are RAW "up to N creatures of
your choice that you can see WITHIN RANGE (60 ft)." Pre-v2.61.1
the v2.59.0 multi-target heal loop healed every target_combatant_id
passed in without checking distance. v2.61.1 adds a per-target
`_distance_ft_between_chars` check at the top of the extras loop;
out-of-range targets are silently dropped + a `feature_used(source=
"heal-out-of-range")` broadcast warns the player.

Test scenarios:
  - Tavik places himself at (350, 350), Krieger at (420, 350) [5 ft]
    and Pip at (1500, 350) [~80 ft on demo grid]. Mass Healing Word
    at slot 3 → Krieger heals normally; Pip skipped + warning
    broadcast fires.
  - Control: same setup but no tokens placed → all targets heal
    (None-fallback path preserved from v2.61.0).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


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
        "id": f"tok_mhrange_{char_id}",
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


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _delete_token(gm_client, char_id):
    """Remove a character's token from the active map.

    NOTE: deletion can break subsequent tests that expect the demo
    tokens to still exist (e.g. test_move calls
    ``/api/campaign/{cid}/tokens`` and asserts on PC tokens being
    present). Tests in this file use this only for tokens that the
    test itself placed AND that aren't referenced elsewhere; for
    demo-seeded tokens (Pip / Tavik / Krieger), prefer
    ``_restore_token`` which moves the token back to a benign
    corner position so the token row stays in the database.
    """
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/token",
    )


async def _restore_token(gm_client, char_id):
    """Move a token back to a safe corner so it's out of the way
    of any aura / range gate but still exists in the active map's
    token list. Used in test cleanup to avoid breaking subsequent
    tests that need the token row to exist.
    """
    await _place_token(gm_client, char_id, 50.0, 50.0)


def _broadcasts_for_source(gm_ws, source: str) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == source
    ]


async def test_mass_healing_word_drops_out_of_range_target(
    gm_client, gm_ws, tavik_rested, krieger_wounded, pip_wounded,
):
    """Tavik at (350, 350), Krieger at (420, 350) [5 ft], Pip at
    (1500, 350) [≈82 ft on the 70 px / 5 ft demo grid].

    Mass Healing Word range is 60 ft. Krieger in range, Pip out.
    Expected: Krieger gets a Disciple of Life uplift broadcast
    (because Tavik is Lv 8 Life Domain — already wired v2.58.0);
    Pip gets an out-of-range warning broadcast; only Krieger heals.
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    pip = pip_wounded
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 45}},
    )

    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)
    await _place_token(gm_client, pip["id"], 1500.0, 350.0)

    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"],
                        hp_current=45, hp_max=51),
        _make_combatant(krieger["name"], krieger["id"],
                        hp_current=40, hp_max=75),
        _make_combatant(pip["name"], pip["id"],
                        hp_current=20, hp_max=47),
    ])
    gm_ws.mark()

    try:
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": TAVIK_MASS_HEALING_WORD_INDEX,
                "slot_level": 3,
                "class_slug": "cleric",
                "target_combatant_ids": [
                    f"tok_mhrange_{krieger['id']}",  # 5 ft — in range
                    f"tok_mhrange_{pip['id']}",      # ~80 ft — out
                ],
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text

        # Out-of-range warning broadcast for Pip.
        warns = _broadcasts_for_source(gm_ws, "heal-out-of-range")
        assert warns, (
            f"expected heal-out-of-range broadcast for Pip; "
            f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
        )
        warn_fn = (warns[0].get("data") or {}).get("feature_name", "")
        assert pip["name"] in warn_fn, (
            f"warning broadcast should name Pip; got: {warn_fn!r}"
        )

        # Krieger should have received the Disciple of Life uplift
        # broadcast (Tavik is Lv 8 Life Domain). Pip should NOT
        # appear in any Disciple of Life broadcast since the loop
        # skipped him.
        dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life")
        krieger_dol = [
            m for m in dol_msgs
            if krieger["name"] in (m.get("data") or {}).get("feature_name", "")
        ]
        pip_dol = [
            m for m in dol_msgs
            if pip["name"] in (m.get("data") or {}).get("feature_name", "")
        ]
        assert krieger_dol, (
            f"expected disciple-of-life broadcast naming Krieger (in range)"
        )
        assert not pip_dol, (
            f"Pip is out of range; should NOT appear in disciple-of-life "
            f"broadcasts: {[(m.get('data') or {}).get('feature_name') for m in pip_dol]}"
        )
    finally:
        # Cleanup: restore tokens to a benign corner rather than
        # deleting them. test_move + other suite tests depend on
        # the demo's Pip/Tavik/Krieger tokens existing in the
        # campaign — deleting breaks those tests.
        await _restore_token(gm_client, tavik["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, pip["id"])


async def test_mass_healing_word_heals_all_when_no_tokens(
    gm_client, gm_ws, tavik_rested, krieger_wounded, pip_wounded,
):
    """Control / backward-compat: no tokens placed → distance helper
    returns None → range gate falls back to "in range" for all
    targets → both Krieger AND Pip get the Disciple of Life uplift.
    Mirrors v2.61.0 fall-back semantics for the auras.
    """
    tavik = tavik_rested
    krieger = krieger_wounded
    pip = pip_wounded
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": 45}},
    )

    # No _place_token calls. The auras + heal loop should fall back
    # to "any in init" since _distance_ft_between_chars returns None.
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
                f"tok_mhrange_{krieger['id']}",
                f"tok_mhrange_{pip['id']}",
            ],
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    warns = _broadcasts_for_source(gm_ws, "heal-out-of-range")
    assert not warns, (
        f"no out-of-range warning when tokens aren't placed; "
        f"got: {[(m.get('data') or {}).get('feature_name') for m in warns]}"
    )

    dol_msgs = _broadcasts_for_source(gm_ws, "disciple-of-life")
    feature_names = [
        (m.get("data") or {}).get("feature_name", "") for m in dol_msgs
    ]
    assert any(krieger["name"] in fn for fn in feature_names), (
        f"expected disciple-of-life broadcast naming Krieger; got: {feature_names}"
    )
    assert any(pip["name"] in fn for fn in feature_names), (
        f"expected disciple-of-life broadcast naming Pip (fallback path); "
        f"got: {feature_names}"
    )
