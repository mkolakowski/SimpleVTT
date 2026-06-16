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


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_berserk_save_installs_buff_on_failed_save(gm_client, krieger):
    """Krieger attuned to the Berserker Axe, takes 10 damage via PATCH
    /sheet-fields (hp_change_reason=damage). Sweep seeds until the DC 15
    WIS save fails → the `berserk` buff appears on his sheet."""
    inv_snap, hp_snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=True,
    )
    try:
        installed = False
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

            data = await _sheet_json(gm_client, krieger["id"])
            sheet = data.get("sheet") or {}
            buffs = _buffs(sheet)
            if any(
                isinstance(b, dict) and b.get("key") == _BERSERK_BUFF_KEY
                for b in buffs
            ):
                installed = True
                break
            # Clear any berserk install (none expected — pass case);
            # also clear concentration buffs not relevant here.
        assert installed, (
            "Across seeds 0..199 the DC 15 WIS save never failed — "
            "the on-damage berserk save may not be firing. Krieger's "
            "WIS save is +1, so seeds with a low d20 should fail."
        )
        # Verify the buff's markers.
        sheet = (await _sheet_json(gm_client, krieger["id"])).get("sheet") or {}
        berserk = next(
            (b for b in _buffs(sheet)
             if isinstance(b, dict) and b.get("key") == _BERSERK_BUFF_KEY),
            None,
        )
        assert berserk is not None
        eff = berserk.get("effects") or {}
        assert eff.get("berserk_active") is True
        assert eff.get("berserk_attack_nearest") is True
        assert berserk.get("source") == "item-berserker-axe"
    finally:
        # Restore HP + inventory.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": hp_snap},
        )
        await _restore_inv(gm_client, krieger["id"], inv_snap)


async def test_berserk_save_does_not_fire_without_attunement(gm_client, krieger):
    """Equipped-but-NOT-attuned axe → on-damage save is gated off and the
    `berserk` buff never installs (across an aggressive seed sweep)."""
    inv_snap, hp_snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=False,
    )
    try:
        for seed in range(0, 50):
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
                json={"hp": {"current": int(hp_snap.get("max") or 75)}},
            )
            await _seed_dice(gm_client, seed)
            try:
                resp = await _damage(
                    gm_client, krieger["id"],
                    new_current=max(0, int(hp_snap.get("max") or 75) - 10),
                    amount=10,
                )
                assert resp.status_code == 200, resp.text
            finally:
                await _seed_dice(gm_client, None)
            data = await _sheet_json(gm_client, krieger["id"])
            sheet = data.get("sheet") or {}
            if any(
                isinstance(b, dict) and b.get("key") == _BERSERK_BUFF_KEY
                for b in _buffs(sheet)
            ):
                raise AssertionError(
                    f"berserk buff installed without attunement (seed {seed}); "
                    f"buffs={_buffs(sheet)!r}"
                )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"hp": hp_snap},
        )
        await _restore_inv(gm_client, krieger["id"], inv_snap)
