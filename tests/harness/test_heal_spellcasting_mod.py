"""v2.59.1 — heal expressions bake the caster's spellcasting modifier.

Pre-v2.59.1, /cast_spell rolled the SRD JSON's bare healing dice
(e.g. Cure Wounds `1d8`) without adding the caster's spellcasting
modifier. RAW: Cure Wounds heals `1d8 + spellcasting modifier`.

`_caster_spellcasting_mod(caster_sheet)` reads the ability slug
from `spellcasting_ability` (or `class_spellcasting`), looks up
the score in `abilities`, returns `(score-10)//2`. The heal-
resolution branch adds this to `heal_rolled` before the Disciple
of Life uplift composition.

Tests:
  - Tavik (WIS 16 = +3) casts Cure Wounds (L1) at Krieger.
    `auto_heal_rolled` should be at least 1 + 3 = 4 (min die +
    mod) and at most 8 + 3 = 11 (max die + mod). Loop 5 casts —
    every roll must be >= 4 (proves the +3 is being added).
  - Pip (no spellcasting ability — Rogue) shouldn't get a +0
    mod added cleanly. Skip since Pip can't cast heal spells.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_CURE_WOUNDS_INDEX = 4


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
        json={"hp": {"current": 20}},
    )
    return krieger


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _make_combatant(name, char_id, hp_current=30, hp_max=75, init=10):
    return {
        "id": f"tok_hw_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_cure_wounds_adds_wis_modifier_to_heal(
    gm_client, tavik_rested, krieger_wounded,
):
    """Tavik (WIS 16 = +3) casts Cure Wounds (L1) at Krieger 5
    times. The /cast_spell response carries ``auto_heal_applied``
    (final HP delta after cap-at-max + Life Domain uplift).

    Pre-v2.59.1 range: 1d8 + 0 (no mod) + 3 (Disciple of Life)
    = [4, 11]. Post-v2.59.1 range: 1d8 + 3 (WIS) + 3 (DoL)
    = [7, 14]. Asserting `>= 7` is the clean proof the modifier
    is now being added (the pre-fix min was 4).

    Krieger starts wounded at 20/75 so cap-at-max never binds.
    """
    tavik = tavik_rested
    krieger = krieger_wounded

    for _ in range(5):
        # Long rest tavik between casts so slots refill.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        # Re-wound Krieger so heals have room to land.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": {"current": 20}},
        )
        await _seed_battle(gm_client, [
            _make_combatant(tavik["name"], tavik["id"],
                            hp_current=51, hp_max=51),
            _make_combatant(krieger["name"], krieger["id"],
                            hp_current=20, hp_max=75),
        ])
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": TAVIK_CURE_WOUNDS_INDEX,
                "slot_level": 1,
                "class_slug": "cleric",
                "target_combatant_id": f"tok_hw_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text
        data = cast_resp.json()
        applied = data.get("auto_heal_applied", 0)
        assert applied >= 7, (
            f"Cure Wounds with WIS +3 (and Disciple of Life +3) should "
            f"apply ≥ 7 HP (1d8 + 3 mod + 3 uplift = min 7); got "
            f"auto_heal_applied={applied}; response: {data}"
        )
        assert applied <= 14, (
            f"Cure Wounds at L1 should apply ≤ 14 HP (8 + 3 + 3); got "
            f"auto_heal_applied={applied}; response: {data}"
        )
