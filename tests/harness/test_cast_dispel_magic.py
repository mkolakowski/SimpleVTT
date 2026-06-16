"""v2.372.0 — Dispel Magic endpoint (RAW PHB p.234, L3 abjuration).

"Choose any creature, object, or magical effect within range. Any
spell of 3rd level or lower on the target ends. For each spell of
4th level or higher on the target, make an ability check using your
spellcasting ability. The DC equals 10 + the spell's level. On a
successful check, the spell ends."

At Higher Levels: cast at 4th+ → auto-end spells of slot level or
lower without a check.

The new `/cast_dispel_magic` endpoint:
- Takes `{character_id, target_combatant_id, buff_key, slot_level,
  class_slug, buff_source_level?}`.
- Validates the caster knows dispel-magic + has the slot + target
  has the named buff.
- Consumes the slot.
- Auto-end if buff_source_level ≤ slot_level, else rolls a check.
- On end, removes the buff via `_remove_buff` (PC) or hub-state
  mutation (NPC).

v1 simplifications: the RAW "any spell on the target" semantics (the
endpoint picks ONE named buff per cast; multi-buff cascade is
GM-narrated by re-calling the endpoint per buff).

Demo fixture: Lyra Sunstrider (Bard Lv 6) is the caster — Dispel
Magic is on her spell list (line 2595 in demo_seed.py). She has
3/3 L3 slots by default. Krieger is the target (his combatant
carries seed buffs).

Tests:
  - Happy: L3 cast vs L1 buff → auto_end True, buff dropped, slot
    consumed.
  - Check path: L3 cast vs L5 buff (rigged via buff_source_level=5)
    → roll fired, DC=15; on success the buff drops, on failure it
    persists. We just assert the roll fired + ended==check_passed.
  - 409 no_slot when caster has no L3 slot remaining.
  - 409 buff_not_found when the buff key isn't on the target.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _mkc(cid, char_id=None, name="X", buffs=None):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 50, "hp_max": 50,
        "buffs": list(buffs or []),
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, lyra, krieger, krieger_buffs=None):
    krieger_tok = f"tok_dispel_krieger_{krieger['id']}"
    lyra_tok = f"tok_dispel_lyra_{lyra['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                _mkc(lyra_tok, lyra["id"], name=lyra["name"]),
                _mkc(krieger_tok, krieger["id"], name=krieger["name"],
                     buffs=krieger_buffs),
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return lyra_tok, krieger_tok


async def _install_test_buff(gm_client, krieger, krieger_tok, buff):
    """Force a named buff onto Krieger's combatant via /battle PUT —
    bypasses the spell-cast install path to keep the test focused on
    Dispel Magic's mechanics."""
    # Re-seed the battle with the buff already on Krieger.
    lyra_tok = f"tok_dispel_lyra_{krieger['id']}_install"  # any unique tok
    # Easiest: get current battle, mutate Krieger's buffs, PUT.
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    state = (r.json() or {}).get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("id") == krieger_tok:
            c["buffs"] = list(c.get("buffs") or []) + [buff]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=state,
    )


async def _krieger_buffs(gm_client, krieger_tok):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    state = (r.json() or {}).get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("id") == krieger_tok:
            return list(c.get("buffs") or [])
    return []


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def lyra(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await _long_rest(gm_client, lyra["id"])
    return lyra


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_dispel_magic_auto_ends_low_level_buff(
    gm_client, lyra, krieger,
):
    """L3 cast vs L1 buff (Bless) → auto_end=True, buff dropped,
    L3 slot consumed (one less)."""
    lyra_tok, krieger_tok = await _seed_battle(gm_client, lyra, krieger)
    # Install a test "bless" buff on Krieger via PUT /battle.
    await _install_test_buff(gm_client, krieger, krieger_tok, {
        "key": "bless",
        "name": "Bless",
        "icon": "🙏",
        "duration_rounds": 100,
        "duration_max": 100,
        "concentration": False,
        "source": "spell-bless",
        "source_spell": "Bless",
        "effects": {"bless_save_bonus": "d4"},
    })
    # Cast Dispel Magic at L3, buff_source_level=1 → auto-end.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_dispel_magic",
        json={
            "character_id": lyra["id"],
            "target_combatant_id": krieger_tok,
            "buff_key": "bless",
            "slot_level": 3,
            "class_slug": "bard",
            "buff_source_level": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_end"] is True
    assert data["ended"] is True
    assert data["slot_used"] >= 1
    # Bless dropped from Krieger.
    buffs_after = await _krieger_buffs(gm_client, krieger_tok)
    assert not any(
        b.get("key") == "bless" for b in buffs_after
    ), f"bless should be dropped; got {buffs_after}"


async def test_dispel_magic_check_path_high_level_buff(
    gm_client, lyra, krieger,
):
    """L3 cast vs an L5 buff (rigged via buff_source_level=5) → roll
    fires, DC=15. Assert the response carries `auto_end: False`,
    `check_total` populated, and `ended == check_passed`."""
    lyra_tok, krieger_tok = await _seed_battle(gm_client, lyra, krieger)
    await _install_test_buff(gm_client, krieger, krieger_tok, {
        "key": "hold-monster",
        "name": "Hold Monster",
        "icon": "🥶",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": False,  # rigged for v1 isolation
        "source": "spell-hold-monster",
        "source_spell": "Hold Monster",
        "effects": [],
    })
    # Seed dice to make the check deterministic.
    await _seed_dice(gm_client, 7)
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_dispel_magic",
            json={
                "character_id": lyra["id"],
                "target_combatant_id": krieger_tok,
                "buff_key": "hold-monster",
                "slot_level": 3,
                "class_slug": "bard",
                "buff_source_level": 5,
            },
        )
    finally:
        await _seed_dice(gm_client, None)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_end"] is False, (
        f"L3 cast vs L5 buff should NOT auto-end; got {data}"
    )
    assert data["check_dc"] == 15
    assert data["check_total"] is not None
    # ended == check_passed.
    assert data["ended"] == data["check_passed"], (
        f"ended ({data['ended']}) should equal check_passed "
        f"({data['check_passed']})"
    )
    # Buff persistence matches the check outcome.
    buffs_after = await _krieger_buffs(gm_client, krieger_tok)
    has_hm = any(
        b.get("key") == "hold-monster" for b in buffs_after
    )
    if data["check_passed"]:
        assert not has_hm, "buff should be dropped on a successful check"
    else:
        assert has_hm, "buff should persist on a failed check"


async def test_dispel_magic_no_slot_returns_409(gm_client, lyra, krieger):
    """Burn all 3 of Lyra's L3 slots via PATCH; the 4th cast attempt
    returns 409 `no_slot`."""
    lyra_tok, krieger_tok = await _seed_battle(gm_client, lyra, krieger)
    await _install_test_buff(gm_client, krieger, krieger_tok, {
        "key": "bless",
        "name": "Bless",
        "icon": "🙏",
        "duration_rounds": 100,
        "duration_max": 100,
        "concentration": False,
        "source": "spell-bless",
        "source_spell": "Bless",
        "effects": {"bless_save_bonus": "d4"},
    })
    # Patch Lyra's L3 slots to used=3/total=3.
    sheet_r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-json",
    )
    sheet = (sheet_r.json() or {}).get("sheet") or {}
    snap = dict(sheet.get("spell_slots") or {})
    new_slots = {**snap}
    new_slots["bard"] = dict(new_slots.get("bard") or {})
    new_slots["bard"]["3"] = {"total": 3, "used": 3}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"spell_slots": new_slots},
    )
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_dispel_magic",
            json={
                "character_id": lyra["id"],
                "target_combatant_id": krieger_tok,
                "buff_key": "bless",
                "slot_level": 3,
                "class_slug": "bard",
                "buff_source_level": 1,
            },
        )
        assert resp.status_code == 409, resp.text
        assert (resp.json() or {}).get("error") == "no_slot"
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"spell_slots": snap},
        )


async def test_dispel_magic_buff_not_found_returns_409(
    gm_client, lyra, krieger,
):
    """Target combatant has no buff with the named key → 409
    `buff_not_found`."""
    lyra_tok, krieger_tok = await _seed_battle(gm_client, lyra, krieger)
    # Krieger has no `bless` buff.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_dispel_magic",
        json={
            "character_id": lyra["id"],
            "target_combatant_id": krieger_tok,
            "buff_key": "bless",
            "slot_level": 3,
            "class_slug": "bard",
            "buff_source_level": 1,
        },
    )
    assert resp.status_code == 409, resp.text
    assert (resp.json() or {}).get("error") == "buff_not_found"
