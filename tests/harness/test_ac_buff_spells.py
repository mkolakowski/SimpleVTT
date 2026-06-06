"""v2.99.422 — Phase 4.3: +AC spell buffs (Mage Armor / Haste).

docs/plans/temp-hp-and-bonuses.md P4.3 — Mage Armor and Haste now have
``_SPELL_BUFF_MAP`` entries carrying ``effects.ac_bonus`` (Mage Armor +3,
Haste +2), so casting them installs a buff that ``_read_target_ac``
already sums into the target's AC at ``/attack`` hit determination.

Mage Armor wasn't in any demo caster's spell list (only a comment
claimed Magnus had it; v2.99.422 adds it to demo_seed at index 11). The
live demo DB was seeded before that, so the fixture PATCHes Magnus's
full spell list (indices 0-10 verbatim + Mage Armor appended at 11, so
other index-based cast tests are unaffected) and gives him an unarmored
base to make the +3 observable.

Tests:
  - Cast Mage Armor on self → `mage-armor` buff installs with
    `ac_bonus: 3`, and `/attack`'s `target_ac` rises by 3.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Magnus Hexbinder's demo spell list (see demo_seed `_warlock_sheet`),
# with Mage Armor appended at index 11. Indices 0-10 match the demo so
# the many other harness tests that cast Magnus's spells by index are
# unaffected by the PATCH below.
_MAGNUS_SPELLS = [
    {"name": "Eldritch Blast", "level": 0, "_slug": "eldritch-blast",
     "prepared": True, "casting_time": "1 action"},
    {"name": "Prestidigitation", "level": 0, "_slug": "prestidigitation",
     "prepared": True, "casting_time": "1 action"},
    {"name": "Mage Hand", "level": 0, "_slug": "mage-hand",
     "prepared": True, "casting_time": "1 action"},
    {"name": "Hex", "level": 1, "_slug": "hex", "prepared": True,
     "casting_time": "1 bonus action", "_concentration": True},
    {"name": "Hellish Rebuke", "level": 1, "_slug": "hellish-rebuke",
     "prepared": True, "casting_time": "1 reaction"},
    {"name": "Burning Hands", "level": 1, "_slug": "burning-hands",
     "prepared": True, "casting_time": "1 action",
     "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)"},
    {"name": "Scorching Ray", "level": 2, "_slug": "scorching-ray",
     "prepared": True, "casting_time": "1 action",
     "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)"},
    {"name": "Mirror Image", "level": 2, "_slug": "mirror-image",
     "prepared": True, "casting_time": "1 action"},
    {"name": "Counterspell", "level": 3, "_slug": "counterspell",
     "prepared": True, "casting_time": "1 reaction"},
    {"name": "Fireball", "level": 3, "_slug": "fireball", "prepared": True,
     "casting_time": "1 action",
     "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)"},
    {"name": "Sleep", "level": 1, "_slug": "sleep", "prepared": True,
     "casting_time": "1 action"},
    {"name": "Mage Armor", "level": 1, "_slug": "mage-armor",
     "prepared": True, "casting_time": "1 action"},
]
MAGE_ARMOR_INDEX = 11


async def _patch_sheet(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def magnus_with_mage_armor(gm_client, roster):
    """Ensure live Magnus has Mage Armor at index 11 (the demo DB was
    seeded before v2.99.422 added it). Indices 0-10 are the demo spells
    verbatim, so no restore is needed."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"spells": _MAGNUS_SPELLS})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_mage_armor_installs_ac_buff_and_raises_ac(
    gm_client, gm_ws, magnus_with_mage_armor,
):
    """Casting Mage Armor installs a `mage-armor` buff (ac_bonus 3) and
    the target's `/attack` AC rises by 3."""
    magnus = magnus_with_mage_armor
    magnus_tok = f"tok_ma_{magnus['id']}"
    attacker_tok = "tok_ma_attacker"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": magnus_tok, "char_id": magnus["id"], "name": magnus["name"],
             "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": attacker_tok, "char_id": None, "name": "Attacker",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Baseline AC: a save-DC "attack" surfaces target_ac without needing
    # a real attacker sheet — use the GM-driven /attack against Magnus
    # from the bare NPC (attack rolls are random but target_ac is the AC
    # read, independent of the roll).
    async def _read_ac():
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": magnus["id"], "attack_index": 0,
                  "target_combatant_id": magnus_tok, "override": True},
        )
        assert a.status_code == 200, a.text
        return a.json()["target_ac"]

    base_ac = await _read_ac()
    assert base_ac is not None

    # Cast Mage Armor on self (warlock pact slot, level 3).
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": magnus["id"], "spell_index": MAGE_ARMOR_INDEX,
              "slot_level": 3, "class_slug": "warlock",
              "target_combatant_id": magnus_tok,
              "target_character_id": magnus["id"],
              "override": True, "override_range": True},
    )
    assert r.status_code == 200, r.text

    bu = await gm_ws.wait_for("buff_update")
    ma = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "mage-armor"), None)
    assert ma is not None, bu["data"]["buffs"]
    assert (ma.get("effects") or {}).get("ac_bonus") == 3

    # AC rose by exactly the +3.
    new_ac = await _read_ac()
    assert new_ac == base_ac + 3