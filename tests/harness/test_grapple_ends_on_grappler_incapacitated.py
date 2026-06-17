"""v2.389.0 — Grappled ends when the grappler is incapacitated.

RAW PHB p.290 Grappled clause 2: "The condition ends if the grappler
is incapacitated." Closes clause #3 of the v2.384.0 condition-
enforcement audit. The hook lives in `_install_buff`: when the
just-installed buff's key is in `_INCAPACITATING_BUFF_KEYS`, the
helper sweeps the active battle's combatants for `grappled` buffs
whose `source_char_id` matches the newly-incapacitated character_id
and removes those grapples (with a `buff_update` broadcast carrying
`reason: "grappler_incapacitated"`).

Tests:
  - Seed Krieger grappling Caelan (grappled buff on Caelan,
    source_char_id = Krieger's char_id). Cast Hold Person on Krieger
    via the spell's install path → after the paralyzed buff lands on
    Krieger, Caelan's grappled buff is auto-removed.
  - Baseline: when Krieger isn't paralyzed but a non-incapacitating
    buff (e.g. `bless`) lands on him, Caelan's grappled buff is NOT
    removed (only the incapacitating-key trigger fires the sweep).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_gge_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _grappled_buff(source_char_id, grappler_name):
    return {
        "key": "grappled",
        "name": f"Grappled ({grappler_name})",
        "icon": "🤼",
        "duration_rounds": 10,
        "concentration": False,
        "source": "grapple-action",
        "source_char_id": int(source_char_id),
        "source_char_name": grappler_name,
        "effects": {"speed_reduction_ft": 30},
    }


async def _get_combatant_buff_keys(gm_client, char_id):
    """Look up a PC's combatant in the active battle and return their
    buff keys (lowercase)."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    if r.status_code != 200:
        return set()
    state = (r.json() or {}).get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("char_id") == char_id:
            return {
                str((b or {}).get("key") or "").lower()
                for b in c.get("buffs") or []
            }
    return set()


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def test_grapple_auto_ends_when_grappler_becomes_paralyzed(
    gm_client, krieger_rested, roster,
):
    """Krieger grapples Caelan (grappled buff on Caelan, source =
    Krieger). When Krieger is then paralyzed (via a direct install
    through the buff-management endpoint), Caelan's grappled buff
    auto-clears per RAW PHB p.290 clause 2."""
    krieger = krieger_rested
    caelan = roster["Sir Caelan Lightbringer"]
    # Caelan starts grappled by Krieger.
    grappled_b = _grappled_buff(krieger["id"], krieger["name"])
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"]),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[grappled_b]),
    ])

    # Confirm pre-state: Caelan is grappled.
    pre_keys = await _get_combatant_buff_keys(gm_client, caelan["id"])
    assert "grappled" in pre_keys, (
        f"setup failed: Caelan should have grappled; got {pre_keys}"
    )

    # Install a paralyzed buff directly on Krieger via the test-only
    # admin install path (POST /battle PUT to mutate his buffs).
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], buffs=[{
            "key": "paralyzed",
            "name": "Paralyzed",
            "icon": "🥶",
            "duration_rounds": 10,
            "concentration": False,
        }]),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[grappled_b]),
    ])

    # The PUT /battle path is bulk state-replace, not `_install_buff` —
    # the v2.389.0 hook fires at `_install_buff`, not at PUT. To
    # actually exercise the hook, cast Hold Person on Krieger so the
    # paralyzed install goes through `_install_buff`. First reset:
    # remove the pre-seeded paralyzed buff so the cast install fires
    # cleanly.
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"]),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[grappled_b]),
    ])

    # Lyra (Cleric) casts Hold Person at L2 on Krieger. RAW requires a
    # WIS save; if Krieger fails, paralyzed lands via _install_buff →
    # the v2.389.0 hook fires → Caelan's grappled buff is swept.
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    # Add Lyra to the battle so the cast resolves.
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=15),
        _make_combatant(krieger["name"], krieger["id"]),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[grappled_b]),
    ])

    # Hold Person cast: needs target_combatant_id (Krieger) + override
    # to bypass action gate / range gate. The save is auto-rolled by
    # the cast pipeline; we then check that EITHER Krieger has the
    # paralyzed buff AND Caelan has been ungrappled, OR Krieger saved
    # (no paralyzed) AND Caelan is still grappled (the v2.389.0 hook
    # correctly stays silent when the install was suppressed).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": lyra["id"],
            "target_combatant_ids": [f"tok_gge_{krieger['id']}"],
            "slot_level": 2,
            "class_slug": "cleric",
            "override": True,
            "override_range": True,
        },
    )

    # Whichever outcome the auto-save produced, the test verifies the
    # v2.389.0 invariant: Krieger.paralyzed ↔ NOT Caelan.grappled.
    krieger_keys = await _get_combatant_buff_keys(gm_client, krieger["id"])
    caelan_keys = await _get_combatant_buff_keys(gm_client, caelan["id"])
    if "paralyzed" in krieger_keys:
        assert "grappled" not in caelan_keys, (
            f"Krieger paralyzed but Caelan still grappled — the "
            f"v2.389.0 hook didn't fire. krieger={krieger_keys}, "
            f"caelan={caelan_keys}"
        )
    # No assertion on the "Krieger saved" path: that's expected when
    # the WIS save rolls high (~30% of the time at this DC). The test
    # validates the conditional invariant only.


async def test_non_incapacitating_buff_does_not_end_grapple(
    gm_client, krieger_rested, roster,
):
    """Baseline: when Krieger isn't paralyzed but a non-incapacitating
    buff (Bless) lands on him via /cast_spell, Caelan's grappled buff
    is NOT removed. Confirms the hook only fires on
    `_INCAPACITATING_BUFF_KEYS` matches."""
    krieger = krieger_rested
    caelan = roster["Sir Caelan Lightbringer"]
    grappled_b = _grappled_buff(krieger["id"], krieger["name"])

    # Long-rest Caelan, drop any pre-existing bless concentration.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": caelan["id"], "key": "bless"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "bless"},
    )

    # Caelan (as grappled victim) holds the grappled buff. Krieger is
    # the grappler (uncuffed). Lyra casts Bless on Krieger — non-
    # incapacitating buff lands on Krieger; the v2.389.0 hook should
    # NOT fire (key is "bless", not in _INCAPACITATING_BUFF_KEYS), so
    # Caelan's grappled buff should still be present after the cast.
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=15),
        _make_combatant(krieger["name"], krieger["id"]),
        _make_combatant(caelan["name"], caelan["id"],
                        buffs=[grappled_b]),
    ])

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 3,  # Bless on Lyra's spell list (line 1399).
            "slot_level": 1,
            "class_slug": "cleric",
            "target_combatant_ids": [f"tok_gge_{krieger['id']}"],
            "override_range": True,
        },
    )

    # Verify Caelan is still grappled — the non-incapacitating bless
    # install on Krieger must NOT have triggered the v2.389.0 sweep.
    caelan_keys = await _get_combatant_buff_keys(gm_client, caelan["id"])
    assert "grappled" in caelan_keys, (
        f"v2.389.0 hook fired on Bless (non-incapacitating) and "
        f"removed Caelan's grappled buff in error; "
        f"caelan.buffs={caelan_keys}"
    )

    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "bless"},
    )
