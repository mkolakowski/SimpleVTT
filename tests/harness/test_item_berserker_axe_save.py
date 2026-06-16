"""v2.363.0 — magic-items: Berserker Axe cursed berserk save (RAW DMG
p.155). Closes the v2.362.0 partial: when the wielder takes damage
while attuned, they must succeed on a DC 15 Wisdom saving throw or go
berserk. New `on_damage_save` payload on `_MAGIC_ITEM_PASSIVES`
(generalized to any future item carrying the same payload shape) +
the `_maybe_item_on_damage_save` helper called from
`_apply_damage_to_combatant`'s PC path AND PATCH /sheet-fields's
damage branch, both next to the existing `_maybe_concentration_save`
trigger. On a failed save the helper installs a `berserk` condition
buff carrying `berserk_active: True` + `berserk_attack_nearest: True`
markers (the auto-attack-nearest AI is GM-narrated in v1).

Demo fixture: Krieger Stonefist (Lv 7, WIS 13 → +1) carries the
Berserker Axe as inert Armory's Remainder loot. Tests PATCH inventory
equipped+attuned, drop Krieger's HP via PATCH /sheet-fields with
`hp_change_reason=damage`, and sweep dice seeds until the DC 15 WIS
save fails (Krieger needs a nat 14+ to pass the DC 15 with +1).

Tests:
  - Across seeds, the on-damage save eventually fails and the
    `berserk` buff installs on Krieger.
  - Inert (no attunement) → no on-damage save fires at all.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_SLUG = "berserker-axe"
_BERSERK_BUFF_KEY = "berserk"
_SAVE_SOURCE = "item-berserker-axe-on-damage-save"


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", hp_max=200):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1, "buffs": [], "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _sheet_json(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json() or {}


async def _snapshot_inv_and_hp(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    sheet = data.get("sheet") or {}
    inv = list(sheet.get("inventory") or [])
    hp = dict(sheet.get("hp") or {})
    return (
        [dict(it) if isinstance(it, dict) else it for it in inv],
        hp,
    )


async def _patch_inv(gm_client, char_id, *, equipped, attuned):
    inv_snap, hp_snap = await _snapshot_inv_and_hp(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv_snap]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Krieger has no berserker-axe inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return inv_snap, hp_snap


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _damage(gm_client, char_id, *, new_current, amount):
    return await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": new_current},
            "hp_change_reason": "damage",
            "damage_amount": amount,
        },
    )


def _buffs(sheet):
    return [
        b for b in ((sheet.get("_buffs_active") or []))
        if isinstance(b, dict)
    ]


async def _clear_berserk(gm_client, char_id):
    """Drop any lingering `berserk` buff (cross-test contamination)
    by force-clearing `_buffs_active` on the sheet. Sheet PATCH works
    whether or not Krieger is in an active battle (the v2.363.1
    end-of-`_maybe_item_on_damage_save` mirror lands buffs on the
    sheet's `_buffs_active`, so the sheet is the canonical pre-test
    state to reset)."""
    try:
        r = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
        )
        if r.status_code != 200:
            return
        sheet = (r.json() or {}).get("sheet") or {}
        active = list(sheet.get("_buffs_active") or [])
        new_active = [
            b for b in active
            if not (isinstance(b, dict) and b.get("key") == _BERSERK_BUFF_KEY)
        ]
        if len(new_active) != len(active):
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
                json={"_buffs_active": new_active},
            )
    except Exception:
        pass


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_berserk_save_installs_buff_on_failed_save(
    gm_client, gm_ws, krieger,
):
    """Krieger attuned + in init, takes 10 damage via PATCH /sheet-fields.
    Sweep seeds until the DC 15 WIS save fails — assert via the
    `feature_used` broadcast that the on_damage_save (a) fired and (b)
    landed on `passed: False` at least once. The broadcast signal is
    per-test (via `gm_ws.mark()`) so cross-test contamination of
    `_buffs_active` is irrelevant. When the save fails, the buff is
    installed (via `_install_buff` → mirrored to sheet); we sanity-check
    the post-loop sheet too."""
    await _clear_berserk(gm_client, krieger["id"])
    inv_snap, hp_snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=True,
    )
    # Seed a battle so the install can reach the combatant in hub state
    # (`_install_buff` requires the character to be in init).
    krieger_cid = f"tok_baxe_save_krieger_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
    ])
    try:
        gm_ws.mark()
        failed_seed = None
        for seed in range(0, 200):
            # Reset HP each iteration so the damage trigger keeps firing.
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
                json={"hp": {"current": int(hp_snap.get("max") or 75)}},
            )
            await _seed_dice(gm_client, seed)
            try:
                cur = int(hp_snap.get("max") or 75)
                resp = await _damage(
                    gm_client, krieger["id"],
                    new_current=max(0, cur - 10), amount=10,
                )
                assert resp.status_code == 200, resp.text
            finally:
                await _seed_dice(gm_client, None)

            this_seed_saves = [
                m for m in gm_ws.buffered("feature_used")
                if (m.get("data") or {}).get("source") == _SAVE_SOURCE
            ]
            failed = [
                m for m in this_seed_saves
                if (m.get("data") or {}).get("passed") is False
            ]
            if failed:
                failed_seed = seed
                break
        assert failed_seed is not None, (
            "Across seeds 0..199 the DC 15 WIS save never failed — "
            "the on-damage berserk save may not be firing. Krieger's "
            "WIS save is +1, so seeds with a low d20 should fail."
        )
        # Sanity-check the buff lands on the sheet via the v2.363.1
        # mirror.
        sheet = (await _sheet_json(gm_client, krieger["id"])).get("sheet") or {}
        berserk = next(
            (b for b in _buffs(sheet)
             if isinstance(b, dict) and b.get("key") == _BERSERK_BUFF_KEY),
            None,
        )
        assert berserk is not None, (
            f"berserk save broadcast fired with passed=False but the buff "
            f"didn't land on the sheet via the v2.363.1 mirror; "
            f"_buffs_active={_buffs(sheet)!r}"
        )
        eff = berserk.get("effects") or {}
        assert eff.get("berserk_active") is True
        assert eff.get("berserk_attack_nearest") is True
        assert berserk.get("source") == "item-berserker-axe"
    finally:
        # Drop the lingering berserk buff so the next test isn't
        # contaminated; restore HP + inventory.
        await _clear_berserk(gm_client, krieger["id"])
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": hp_snap},
        )
        await _restore_inv(gm_client, krieger["id"], inv_snap)


async def test_berserk_save_does_not_fire_without_attunement(gm_client, gm_ws, krieger):
    """Equipped-but-NOT-attuned axe → on-damage save is gated off: the
    `_maybe_item_on_damage_save` helper never broadcasts the
    `item-berserker-axe-on-damage-save` feature_used audit entry. The
    broadcast presence (not the sheet state) is the canonical signal
    here so prior-test contamination of `_buffs_active` doesn't
    confuse the assertion."""
    inv_snap, hp_snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=False,
    )
    try:
        gm_ws.mark()
        await _seed_dice(gm_client, 0)
        try:
            resp = await _damage(
                gm_client, krieger["id"],
                new_current=max(0, int(hp_snap.get("max") or 75) - 10),
                amount=10,
            )
            assert resp.status_code == 200, resp.text
        finally:
            await _seed_dice(gm_client, None)
        fired = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == _SAVE_SOURCE
        ]
        assert fired == [], (
            f"berserk on-damage save broadcast fired without attunement: "
            f"{fired!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": hp_snap},
        )
        await _restore_inv(gm_client, krieger["id"], inv_snap)
