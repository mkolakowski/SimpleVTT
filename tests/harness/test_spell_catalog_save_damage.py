"""Phase 2A backfill — save-for-half damage assertions.

Phase 2A v1 (`test_spell_catalog_damage.py`) covers attack-roll damage;
v2.182.8 (`test_spell_catalog_multibeam.py`) covers multi-beam. This
file backfills the **save-for-half** category — spells that roll damage
the target halves on a successful save (Fireball, Lightning Bolt, Cone
of Cold, …). The engine rolls that damage server-side into
``auto_save_damage_rolled`` (the FULL pre-halving roll), but only when
``campaign.auto_apply_damage`` is on and the target is an NPC. So this
test flips that flag via the TEST_MODE ``/api/test/campaign/{id}/flags``
endpoint, casts each spell at an NPC, range-checks the rolled damage
against the spell's dice band, asserts the damage type, and restores the
flag in a ``finally``.

Cantrips (Sacred Flame, Poison Spray) exercise the save block's
caster-level tier scaling: Thalindra is Wizard L5, so Sacred Flame rolls
2d8 (not the base 1d8) and Poison Spray 2d12. A content edit to the
``damage_scaling`` table is caught here.

Same scratch-caster bulk-inject scaffolding as the other Phase 2 files:
patch Thalindra with the whole catalog + abundant slots, seed one very-
high-HP NPC, loop the subset. Range-check only — exact-value assertion
via the TEST_MODE dice seed is the same filed Phase 2A.2 follow-up.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_assert import assert_damage_in_range
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# slug -> (slot_level, at-level damage expr for Thalindra @ Wizard L5,
# damage type). Leveled spells cast at their base slot (no upcast);
# cantrips carry their L5 tier expression.
_CASES: dict[str, dict] = {
    "fireball": {"slot": 3, "expr": "8d6", "type": "fire"},
    "lightning-bolt": {"slot": 3, "expr": "8d6", "type": "lightning"},
    "burning-hands": {"slot": 1, "expr": "3d6", "type": "fire"},
    "thunderwave": {"slot": 1, "expr": "2d8", "type": "thunder"},
    "shatter": {"slot": 2, "expr": "3d8", "type": "thunder"},
    "cone-of-cold": {"slot": 5, "expr": "8d8", "type": "cold"},
    "sacred-flame": {"slot": 0, "expr": "2d8", "type": "radiant"},
    "poison-spray": {"slot": 0, "expr": "2d12", "type": "poison"},
}


def _all_entries(spells: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in spells:
        slug = (s.get("slug") or "").strip()
        if not slug:
            continue
        out.append({
            "name": s.get("name") or slug,
            "_slug": slug,
            "level": int(s.get("level_int") or 0),
            "class": _SCRATCH_CLASS,
            "prepared": True,
            "casting_time": s.get("casting_time") or "1 action",
        })
    return out


def _abundant_slots() -> dict:
    return {_SCRATCH_CLASS: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


async def _seed_bandit(gm_client) -> str:
    """One very-high-HP NPC so the damaging casts in a row don't drop it."""
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    cid = "tok_savedmgcatalog_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cid, "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Save Damage Target",
                "initiative": 5, "hp_current": 999999, "hp_max": 999999,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return cid


async def test_every_save_spell_rolls_damage_in_range(gm_client, roster):
    """With auto-apply on, cast each save-for-half spell at an NPC and
    assert ``auto_save_damage_rolled`` (the full pre-halving roll) is in
    the dice band and the damage type matches the catalog."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}

    spells = load_all_spells()
    entries = _all_entries(spells)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    by_slug = {(s.get("slug") or ""): s for s in spells}

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    # Capture + flip auto_apply_damage so the save block rolls damage.
    orig_flag = bool((await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )).json()["auto_apply_damage"])
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": True},
    )

    failures: list[str] = []
    asserted = 0
    try:
        target_id = await _seed_bandit(gm_client)
        for slug, want in _CASES.items():
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                failures.append(f"{slug}: not in catalog")
                continue
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": want["slot"],
                    "class_slug": _SCRATCH_CLASS,
                    "target_combatant_id": target_id,
                    "target_name": "Save Damage Target",
                    "override": True,
                },
            )
            if resp.status_code != 200:
                failures.append(f"{slug}: HTTP {resp.status_code} {resp.text[:120]}")
                continue
            data = resp.json()
            rolled = int(data.get("auto_save_damage_rolled") or 0)
            if rolled <= 0:
                failures.append(
                    f"{slug}: auto_save_damage_rolled={rolled} (expected a roll; "
                    f"auto_save_passed={data.get('auto_save_passed')!r})"
                )
                continue
            try:
                assert_damage_in_range(
                    rolled, want["expr"], spell_name=slug, slot_level=want["slot"],
                )
            except AssertionError as exc:
                failures.append(str(exc))
            observed_type = (data.get("auto_save_damage_type") or "").strip().lower()
            if observed_type and observed_type != want["type"]:
                failures.append(
                    f"{slug}: damage type {observed_type!r} != {want['type']!r}"
                )
            asserted += 1
    finally:
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": orig_flag},
        )
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= len(_CASES), (
        f"only asserted {asserted}/{len(_CASES)} save-damage spells"
    )
    assert not failures, (
        f"{len(failures)} save-damage failures (content drift):\n  "
        + "\n  ".join(failures)
    )


def test_save_damage_catalog_subset_present():
    """Guard: every save-damage slug resolves to a catalog spell that
    still carries a save_ability + damage action (no attack roll)."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    missing = [s for s in _CASES if s not in by_slug]
    assert not missing, f"save-damage slugs absent from catalog: {missing}"
    for slug in _CASES:
        a = (by_slug[slug].get("actions") or [{}])[0]
        assert a.get("save_ability"), f"{slug}: lost its save_ability"
        assert a.get("damage"), f"{slug}: lost its damage expression"
        assert not a.get("attack_roll"), f"{slug}: unexpectedly has attack_roll"
