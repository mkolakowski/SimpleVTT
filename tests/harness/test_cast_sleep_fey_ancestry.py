"""v2.99.15 — (D) Phase 3 first-ship: Fey Ancestry sleep immunity.

RAW Fey Ancestry second sentence (PHB p.23, Elf race trait):
"Magic can't put you to sleep." This is a TRUE install-time
immunity — distinct from the v2.99.11 charm-save advantage half
(which is `_race_grants_save_advantage` construction-time). The
Sleep spell has NO save (HP-pool based) so the gate has to fire
BEFORE the spell's HP pool ever counts the target's HP.

Wire site: the existing v2.49.64 `_is_sleep_immune` helper already
centralized RAW Sleep immunity (undead + charm-immune); v2.99.15
extends it to read the race slug via `_race_slug_from_sheet` and
returns `(True, "fey-ancestry")` for `elf` / `half-elf` targets.
Sleep target walker silently filters Fey-Ancestry'd creatures into
the `unaffected` list with `reason: "fey-ancestry"`.

Tests:
  - Elf target (Thalindra): unaffected with reason="fey-ancestry";
    even with a generous pool and low HP, never lands in affected.
  - Half-Elf target (Lyra herself as the caster's own target —
    Sleep can target the caster RAW): same gate, same reason.
  - Wood Elf target (Mira / Kael): same gate — slug normalizer
    folds Wood/High/Dark Elf into "elf".
  - Halfling target (Pip): NOT immune; affected baseline regression
    guard to confirm non-Fey-Ancestry PCs still get put to sleep.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _pc(char, tid_prefix: str, hp: int = 10):
    """Build a minimal PC combatant. Sleep walks ascending HP, so
    low-HP targets fall first. Default 10 HP fits easily under a
    5d8 pool minimum.
    """
    return {
        "id": f"{tid_prefix}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    """Lyra Sunstrider — Half-Elf Bard Lv 6. Sleep is on her spell
    list (v2.49.63 demo seed addition for Bard list)."""
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


async def test_elf_target_immune_via_fey_ancestry(
    gm_client, roster, lyra_rested,
):
    """Lyra casts Sleep at Thalindra (Elf Wizard). Even with a
    generous L2 pool (7d8 = min 7 HP) and Thalindra at low HP, the
    Fey Ancestry gate fires AT IMMUNITY CHECK time — Thalindra
    lands in `unaffected` with reason="fey-ancestry", her HP never
    counts against the pool.
    """
    lyra = lyra_rested
    thalindra = roster["Thalindra Moonwhisper"]
    th_id = f"tok_fey_th_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _pc(lyra, "tok_fey_caster"),
        _pc(thalindra, "tok_fey_th", hp=5),  # well below pool min
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": lyra["id"],
            "class_slug": "bard",
            "slot_level": 2,  # 7d8 pool (min 7) — plenty for 5 HP
            "target_combatant_ids": [th_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Thalindra should NOT be affected.
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert th_id not in affected_ids, (
        f"Thalindra (Elf) should be immune via Fey Ancestry; "
        f"got affected={affected_ids}"
    )
    # And should be in unaffected with the Fey Ancestry reason.
    th_entry = next(
        (u for u in body["unaffected"] if u["combatant_id"] == th_id), None,
    )
    assert th_entry is not None, (
        f"Thalindra should be in unaffected; got {body['unaffected']}"
    )
    assert th_entry["reason"] == "fey-ancestry", th_entry


async def test_half_elf_target_immune_via_fey_ancestry(
    gm_client, roster, lyra_rested,
):
    """Lyra is Half-Elf. RAW Sleep can target the caster's allies
    (Lyra can target herself with Sleep). Confirms the gate covers
    Half-Elf via the `half-elf` slug branch in `_RACE_SAVE_ADVANTAGES`
    and `_is_sleep_immune`.
    """
    lyra = lyra_rested
    lyra_tid = f"tok_fey_caster_{lyra['id']}"
    await _seed_battle(gm_client, [
        _pc(lyra, "tok_fey_caster", hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": lyra["id"],
            "class_slug": "bard",
            "slot_level": 2,
            "target_combatant_ids": [lyra_tid],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert lyra_tid not in affected_ids, (
        f"Lyra (Half-Elf) should be immune via Fey Ancestry; "
        f"got affected={affected_ids}"
    )
    entry = next(
        (u for u in body["unaffected"] if u["combatant_id"] == lyra_tid), None,
    )
    assert entry is not None
    assert entry["reason"] == "fey-ancestry", entry


async def test_wood_elf_target_immune_via_fey_ancestry(
    gm_client, roster, lyra_rested,
):
    """Mira (Wood Elf Druid) — confirms the slug normalizer folds
    "Wood Elf" → "elf" for the Fey Ancestry gate.
    """
    lyra = lyra_rested
    mira = roster["Mira Greenleaf"]
    mira_tid = f"tok_fey_mira_{mira['id']}"
    await _seed_battle(gm_client, [
        _pc(lyra, "tok_fey_caster"),
        _pc(mira, "tok_fey_mira", hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": lyra["id"],
            "class_slug": "bard",
            "slot_level": 2,
            "target_combatant_ids": [mira_tid],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert mira_tid not in affected_ids, (
        f"Mira (Wood Elf) should be immune via Fey Ancestry; "
        f"got affected={affected_ids}"
    )
    entry = next(
        (u for u in body["unaffected"] if u["combatant_id"] == mira_tid), None,
    )
    assert entry is not None
    assert entry["reason"] == "fey-ancestry", entry


async def test_halfling_target_NOT_immune(
    gm_client, roster, lyra_rested,
):
    """Control: Pip (Halfling Rogue) has no Fey Ancestry. Sleep
    affects him normally — regression guard to confirm the v2.99.15
    immunity gate didn't over-apply.
    """
    lyra = lyra_rested
    pip = roster["Pip Quickfingers"]
    pip_tid = f"tok_fey_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _pc(lyra, "tok_fey_caster"),
        _pc(pip, "tok_fey_pip", hp=5),  # well below pool min
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": lyra["id"],
            "class_slug": "bard",
            "slot_level": 2,
            "target_combatant_ids": [pip_tid],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    affected_ids = [a["combatant_id"] for a in body["affected"]]
    assert pip_tid in affected_ids, (
        f"Pip (Halfling) should be affected by Sleep; "
        f"got affected={affected_ids}, unaffected={body['unaffected']}"
    )
