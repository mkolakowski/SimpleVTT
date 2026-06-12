"""Phase 3 — buff *effect* validation (not just install).

Phase 2F (`test_spell_catalog_buff_install.py`) and 2F-2
(`test_spell_catalog_conditions.py`) prove a buff-installing spell lands
its buff on the target. This file closes the next gap: the installed
buff's **mechanical effect during play** is actually applied — and applied
by the exact amount the spell's RAW declares.

The headline slip this guards (see docs/plans/spell-validation-suite.md
Phase 3): a content edit flips Bless from `+1d4` to `+1d6` on attacks but
the engine's attack-roll uplift still hard-codes `+1d4`. The buff installs
correctly, the chip shows correctly, yet the auto-uplift on the attack is
silently wrong. An install-only test sails right past that.

Phase 3a covers the two auto-applied attack-roll uplifts — Bless (+1d4)
and Bane (-1d4) — and Phase 3b extends the same exact check to the
**save** side (Bless/Bane also add/subtract a d4 on saving throws, RAW).
Both use an *exact* check rather than a "token appears" check. The trick:
roll the same d20 twice under the same dice seed, once with the buff and
once without. The d20 is the first draw in both casts (identical seed →
identical d20) and the flat modifier is constant, so the only delta is the
buff die. We then assert that delta equals exactly the d4 value the engine
prints in the buffed breakdown, with the registry-declared sign. A
regression that changes "1d4" → "1d6", drops the uplift, or flips the
sign moves the delta and fails here.

- 3a (attack): the buff is pre-seeded into the *attacker's* combatant;
  `/attack` appends the suffix to the d20 to-hit expression via
  `_attacker_has_bless` / `_attacker_has_bane`. Delta = `attack_total`
  with minus without.
- 3b (save): the buff is pre-seeded into the *saver's* (NPC target's)
  combatant; a save spell cast at it rolls the NPC save server-side and
  `_saver_bless_bane_save_suffix` appends the d4. Delta =
  `auto_save_rolled` with minus without.

Phase 3c covers the flat-AC buffs (Shield of Faith / Mage Armor / Haste);
the boosted-minus-baseline `target_ac` delta must equal the registry
`ac_bonus`. Phase 3d covers the weapon-hit damage riders (Hunter's Mark /
Hex): a real cast installs a `weapon_hit_bonus_dice: "1d6"` rider on the
caster keyed to the target, and the caster's `/attack` against that target
surfaces the rolled die in `auto_uplifts` under `source == <buff key>`. The
gate pins the rider die (`1d6`) and Hex's necrotic type, so a registry edit
to the die or damage type fails it.

Both pre-seed the buff directly via PUT /battle (off the live combatant's
`buffs` list — no `effects` gating, no save-fail loop), so the checks are
fully deterministic. The catalog anchor (`test_*_present_in_catalog`)
ties the registry to the real spell JSON so a renamed/removed spell trips
the gate too.
"""
from __future__ import annotations

import re

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

# Each entry: spell slug → the attacker-side buff it installs, the sign of
# its attack-roll uplift, and the die the engine appends. Only the two
# auto-applied attack-roll uplifts live here (Phase 3a); the save-side and
# AC/speed effects are filed for later Phase 3 slices.
_ATTACK_UPLIFT_BUFFS = {
    "bless": {"buff_key": "bless", "sign": +1, "die": "1d4"},
    "bane": {"buff_key": "baned", "sign": -1, "die": "1d4"},
}

_ATTACKER = "Krieger Stonefist"  # Barbarian, greataxe at attack_index 0.

_D4_TOKEN = re.compile(r"1d4\[(\d+)\]=(\d+)")

# Phase 3c — auto-applied flat AC buffs. Each value mirrors the spell's
# `_SPELL_BUFF_MAP` entry's `effects.ac_bonus`, summed into `target_ac` by
# `_read_target_ac`. The buff is installed by a *real cast* (not pre-seeded)
# so a registry edit to the ac_bonus value is what the gate catches.
_AC_BONUS_BUFFS = {
    "shield-of-faith": 2,
    "mage-armor": 3,
    "haste": 2,
}

_AC_CASTER = "Thalindra Moonwhisper"
_AC_CASTER_CLASS = "wizard"
_AC_ATTACKER = "Pip Quickfingers"
_AC_TARGET = "Krieger Stonefist"


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
            "class": _AC_CASTER_CLASS,
            "prepared": True,
            "casting_time": s.get("casting_time") or "1 action",
        })
    return out


def _abundant_slots() -> dict:
    return {_AC_CASTER_CLASS: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


def _buff_payload(buff_key: str, attacker_id: int) -> dict:
    return {
        "key": buff_key,
        "name": buff_key.title(),
        "icon": "✨",
        "duration_rounds": 10,
        "duration_max": 10,
        "concentration": True,
        "source_char_id": attacker_id,
        "source_char_name": _ATTACKER,
    }


async def _seed_attacker(gm_client, attacker, *, buff_key: str | None) -> str:
    """Drop the attacker into a fresh battle as the sole combatant, with
    or without a pre-seeded attack-uplift buff. Returns its token id."""
    tok = f"tok_buffeff_{attacker['id']}"
    buffs = [_buff_payload(buff_key, attacker["id"])] if buff_key else []
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": tok, "char_id": attacker["id"], "name": attacker["name"],
                "initiative": 10, "hp_current": 60, "hp_max": 60,
                "buffs": buffs,
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return tok


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _attack(gm_client, attacker_id: int) -> dict:
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": attacker_id, "attack_index": 0, "override": True},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_attack_uplift_buffs_present_in_catalog():
    """Catalog anchor: every spell in the attack-uplift registry is a real
    catalog spell. A renamed/removed Bless or Bane trips this before the
    behavioural test even runs."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    missing = [slug for slug in _ATTACK_UPLIFT_BUFFS if slug not in by_slug]
    assert not missing, f"attack-uplift spells absent from catalog: {missing}"


async def test_bless_bane_attack_uplift_contribution_is_exact(gm_client, roster):
    """For Bless (+1d4) and Bane (-1d4): roll the same attack with and
    without the buff under one dice seed, and assert the attack-total delta
    equals exactly the buff die the engine printed, with the right sign.

    The same-seed pair holds the d20 + flat attack bonus constant, so the
    delta isolates the buff die — an exact end-to-end check that the
    installed buff actually moves the attack roll by its RAW amount.
    """
    attacker = roster[_ATTACKER]
    failures: list[str] = []
    checked = 0
    try:
        for slug, spec in _ATTACK_UPLIFT_BUFFS.items():
            seed = 31000 + checked

            # With the buff: parse the printed d4 value from the breakdown.
            await _seed_attacker(gm_client, attacker, buff_key=spec["buff_key"])
            await _seed_dice(gm_client, seed)
            with_data = await _attack(gm_client, attacker["id"])
            with_total = with_data["attack_total"]
            with_bd = with_data["attack_breakdown"]
            m = _D4_TOKEN.search(with_bd or "")
            if not m:
                failures.append(f"{slug}: no 1d4 token in buffed breakdown {with_bd!r}")
                continue
            d4_rolled, d4_sub = int(m.group(1)), int(m.group(2))
            if not (1 <= d4_rolled <= 4):
                failures.append(f"{slug}: d4 roll {d4_rolled} out of [1,4] ({with_bd!r})")
            if d4_rolled != d4_sub:
                failures.append(f"{slug}: d4 token {d4_rolled} != subtotal {d4_sub} ({with_bd!r})")
            # Sign rendering: Bless prints a leading-space '+', Bane a '-'.
            if spec["sign"] < 0 and "-1d4[" not in with_bd:
                failures.append(f"{slug}: expected '-1d4[' (negative die) in {with_bd!r}")
            if spec["sign"] > 0 and "-1d4[" in with_bd:
                failures.append(f"{slug}: unexpected '-1d4[' on a positive-uplift spell ({with_bd!r})")

            # Without the buff: same seed → same d20 + flat bonus.
            await _seed_attacker(gm_client, attacker, buff_key=None)
            await _seed_dice(gm_client, seed)
            without_data = await _attack(gm_client, attacker["id"])
            without_total = without_data["attack_total"]
            if "1d4[" in (without_data.get("attack_breakdown") or ""):
                failures.append(
                    f"{slug}: unbuffed attack unexpectedly carries a 1d4 token: "
                    f"{without_data['attack_breakdown']!r}"
                )

            expected_delta = spec["sign"] * d4_rolled
            actual_delta = with_total - without_total
            if actual_delta != expected_delta:
                failures.append(
                    f"{slug}: attack-total delta {actual_delta} != expected "
                    f"{expected_delta} (sign {spec['sign']:+d} × d4 {d4_rolled}); "
                    f"with={with_total} ({with_bd!r}), without={without_total} "
                    f"({without_data['attack_breakdown']!r})"
                )
            checked += 1
    finally:
        await _seed_dice(gm_client, None)

    assert checked == len(_ATTACK_UPLIFT_BUFFS), (
        f"only exercised {checked}/{len(_ATTACK_UPLIFT_BUFFS)} attack-uplift buffs"
    )
    assert not failures, (
        f"{len(failures)} buff-effect failures:\n  " + "\n  ".join(failures)
    )


# --- Phase 3b: save-side uplift ---------------------------------------------

# Same Bless (+1d4) / Bane (-1d4) dice, applied to the *saver's* d20 by
# `_saver_bless_bane_save_suffix` when a save spell is cast at an NPC that
# carries the buff. Reuses the attack registry's sign + die.
_SAVE_CASTER = "Lyra Sunstrider"   # Bard; Hold Person at spell_index 11.
_HOLD_PERSON_INDEX = 11            # Lyra's Hold Person (L2, WIS save, no damage).


async def _seed_save_battle(gm_client, caster, bandit_tmpl_id, *, buff_key: str | None) -> tuple[str, str]:
    """Battle with the caster + one high-HP bandit target that optionally
    carries a save-uplift buff. Returns (caster_tok, target_tok)."""
    caster_tok = f"tok_buffsave_caster_{caster['id']}"
    target_tok = "tok_buffsave_target"
    buffs = [_buff_payload(buff_key, caster["id"])] if buff_key else []
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": caster_tok, "char_id": caster["id"], "name": caster["name"],
                 "initiative": 12, "hp_current": 35, "hp_max": 35, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": target_tok, "char_id": None, "token_template_id": bandit_tmpl_id,
                 "name": "Save Uplift Target", "initiative": 6,
                 "hp_current": 999999, "hp_max": 999999, "buffs": buffs,
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return caster_tok, target_tok


async def test_bless_bane_save_uplift_contribution_is_exact(gm_client, roster):
    """Save-side mirror of the attack gate: a save spell (Hold Person) cast
    at an NPC carrying Bless / Bane rolls the NPC save server-side with the
    d4 suffix. Same-seed with/without-buff casts hold the NPC's d20 + save
    mod constant, so the `auto_save_rolled` delta isolates the buff die,
    which must equal exactly the printed d4 × the registry sign.
    """
    caster = roster[_SAVE_CASTER]
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())

    failures: list[str] = []
    checked = 0
    try:
        for slug, spec in _ATTACK_UPLIFT_BUFFS.items():
            seed = 42000 + checked

            async def _cast_hold_person() -> dict:
                r = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                    json={
                        "character_id": caster["id"],
                        "spell_index": _HOLD_PERSON_INDEX,
                        "slot_level": 2,
                        "class_slug": "bard",
                        "target_combatant_id": "tok_buffsave_target",
                        "target_name": "Save Uplift Target",
                        "override": True,
                        "override_range": True,
                    },
                )
                assert r.status_code == 200, r.text
                return r.json()

            # With the buff on the saver. Long-rest first so the L2 slot is
            # available; the dice seed is set *after* the rest so the save
            # roll stays deterministic across the pair.
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
                json={"type": "long"},
            )
            await _seed_save_battle(gm_client, caster, bandit["id"], buff_key=spec["buff_key"])
            await _seed_dice(gm_client, seed)
            with_data = await _cast_hold_person()
            if with_data.get("auto_save_target_kind") != "npc":
                failures.append(f"{slug}: expected NPC auto-save, got {with_data.get('auto_save_target_kind')!r}")
                continue
            with_rolled = int(with_data.get("auto_save_rolled") or 0)
            with_bd = with_data.get("auto_save_breakdown") or ""
            m = _D4_TOKEN.search(with_bd)
            if not m:
                failures.append(f"{slug}: no 1d4 token in buffed save breakdown {with_bd!r}")
                continue
            d4_rolled, d4_sub = int(m.group(1)), int(m.group(2))
            if not (1 <= d4_rolled <= 4):
                failures.append(f"{slug}: save d4 roll {d4_rolled} out of [1,4] ({with_bd!r})")
            if d4_rolled != d4_sub:
                failures.append(f"{slug}: save d4 token {d4_rolled} != subtotal {d4_sub} ({with_bd!r})")
            if spec["sign"] < 0 and "-1d4[" not in with_bd:
                failures.append(f"{slug}: expected '-1d4[' in save breakdown {with_bd!r}")
            if spec["sign"] > 0 and "-1d4[" in with_bd:
                failures.append(f"{slug}: unexpected '-1d4[' on a positive save uplift ({with_bd!r})")

            # Without the buff — same seed → same NPC d20 + save mod.
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
                json={"type": "long"},
            )
            await _seed_save_battle(gm_client, caster, bandit["id"], buff_key=None)
            await _seed_dice(gm_client, seed)
            without_data = await _cast_hold_person()
            without_rolled = int(without_data.get("auto_save_rolled") or 0)
            if "1d4[" in (without_data.get("auto_save_breakdown") or ""):
                failures.append(
                    f"{slug}: unbuffed save unexpectedly carries a 1d4 token: "
                    f"{without_data.get('auto_save_breakdown')!r}"
                )

            expected_delta = spec["sign"] * d4_rolled
            actual_delta = with_rolled - without_rolled
            if actual_delta != expected_delta:
                failures.append(
                    f"{slug}: save-total delta {actual_delta} != expected "
                    f"{expected_delta} (sign {spec['sign']:+d} × d4 {d4_rolled}); "
                    f"with={with_rolled} ({with_bd!r}), without={without_rolled} "
                    f"({without_data.get('auto_save_breakdown')!r})"
                )
            checked += 1
    finally:
        await _seed_dice(gm_client, None)

    assert checked == len(_ATTACK_UPLIFT_BUFFS), (
        f"only exercised {checked}/{len(_ATTACK_UPLIFT_BUFFS)} save-uplift buffs"
    )
    assert not failures, (
        f"{len(failures)} save buff-effect failures:\n  " + "\n  ".join(failures)
    )


# --- Phase 3c: flat AC buffs ------------------------------------------------

async def _ac_seed_battle(gm_client, caster, attacker, target) -> None:
    """Caster + attacker + buffed target, all with empty buffs."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_acbuff_caster_{caster['id']}", "char_id": caster["id"],
                 "name": caster["name"], "initiative": 20, "hp_current": 30, "hp_max": 30,
                 "buffs": [], "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": f"tok_acbuff_atk_{attacker['id']}", "char_id": attacker["id"],
                 "name": attacker["name"], "initiative": 14, "hp_current": 40, "hp_max": 40,
                 "buffs": [], "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": f"tok_acbuff_tgt_{target['id']}", "char_id": target["id"],
                 "name": target["name"], "initiative": 8, "hp_current": 60, "hp_max": 60,
                 "buffs": [], "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _ac_target_buffs(gm_client, target_char_id: int) -> list[dict]:
    got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
    tgt = next((c for c in combs if c.get("char_id") == target_char_id), {})
    return [b for b in (tgt.get("buffs") or []) if isinstance(b, dict)]


async def test_ac_buff_spells_present_in_catalog():
    """Catalog anchor for the AC-buff registry."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    missing = [slug for slug in _AC_BONUS_BUFFS if slug not in by_slug]
    assert not missing, f"AC-buff spells absent from catalog: {missing}"


async def test_ac_buff_spells_apply_exact_ac_bonus(gm_client, roster):
    """For Shield of Faith (+2), Mage Armor (+3), Haste (+2): cast the
    spell on a target, attack the target before and after, and assert
    `target_ac` rises by exactly the spell's RAW `ac_bonus`.

    The buff is installed by a *real cast* (not pre-seeded), so the value
    that drives the delta comes from `_SPELL_BUFF_MAP[slug].effects.ac_bonus`
    — a registry edit to that number, or a dropped AC hook, fails the gate.
    """
    caster = roster[_AC_CASTER]
    attacker = roster[_AC_ATTACKER]
    target = roster[_AC_TARGET]
    cid = caster["id"]

    snap = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json")
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

    async def _attack_target() -> int:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker["id"], "attack_index": 0,
                "target_combatant_id": f"tok_acbuff_tgt_{target['id']}",
                "target_character_id": target["id"], "target_name": target["name"],
                "override": True, "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        return int(r.json()["target_ac"])

    failures: list[str] = []
    checked = 0
    try:
        for slug, ac_bonus in _AC_BONUS_BUFFS.items():
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                failures.append(f"{slug}: not in catalog")
                continue

            # Fresh battle (clears any prior buff) → baseline AC.
            await _ac_seed_battle(gm_client, caster, attacker, target)
            baseline_ac = await _attack_target()

            cast = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid, "spell_index": idx,
                    "slot_level": int(spell.get("level_int") or 1) or 1,
                    "class_slug": _AC_CASTER_CLASS,
                    "target_character_id": target["id"],
                    "target_combatant_id": f"tok_acbuff_tgt_{target['id']}",
                    "target_name": target["name"],
                    "override": True, "override_range": True,
                },
            )
            if cast.status_code != 200:
                failures.append(f"{slug}: cast HTTP {cast.status_code} {cast.text[:120]}")
                continue
            buffs = await _ac_target_buffs(gm_client, target["id"])
            if not any(b.get("key") == slug for b in buffs):
                failures.append(
                    f"{slug}: buff not installed on target; keys {[b.get('key') for b in buffs]}"
                )
                continue

            boosted_ac = await _attack_target()
            if boosted_ac - baseline_ac != ac_bonus:
                failures.append(
                    f"{slug}: target_ac delta {boosted_ac - baseline_ac} != expected "
                    f"+{ac_bonus} (baseline={baseline_ac}, boosted={boosted_ac})"
                )
            checked += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert checked == len(_AC_BONUS_BUFFS), (
        f"only exercised {checked}/{len(_AC_BONUS_BUFFS)} AC-buff spells"
    )
    assert not failures, (
        f"{len(failures)} AC buff-effect failures:\n  " + "\n  ".join(failures)
    )


# --- Phase 3d: weapon-hit damage riders -------------------------------------

# Hunter's Mark / Hex each install a concentration buff on the *caster*
# carrying `effects.weapon_hit_bonus_dice: "1d6"` keyed to a target. When the
# caster attacks that target, `_compute_attack_auto_uplifts` rolls the die and
# surfaces it in the /attack response's `auto_uplifts` under `source == key`.
# Installed by a real cast through the dedicated endpoint, so the gate catches
# a registry edit to the rider die or its damage type. `damage_type=None`
# means "defaults to the weapon's type" (Hunter's Mark), so the gate only
# asserts a non-empty type there; Hex pins necrotic. `catalog=False` marks an
# engine-only spell that isn't in the open SRD JSON layer (Hex is PHB-only) —
# its behaviour is still gated, but it's excluded from the catalog anchor.
_HIT_RIDER_BUFFS = {
    "hunters-mark": {
        "key": "hunters-mark", "endpoint": "cast_hunters_mark",
        "caster": "Rowan Quickbow", "die": "1d6", "damage_type": None,
        "body_extra": {}, "catalog": True,
    },
    "hex": {
        "key": "hex", "endpoint": "cast_hex",
        "caster": "Magnus Hexbinder", "die": "1d6", "damage_type": "necrotic",
        "body_extra": {"ability": "STR"}, "catalog": False,
    },
}

_HIT_RIDER_TOKEN = re.compile(r"1d6\[(\d+)\]=(\d+)")
_HIT_RIDER_TARGET = "Krieger Stonefist"  # full HP so Colossus Slayer stays dark.


async def _rider_seed_battle(gm_client, caster, target) -> str:
    """Caster (also the attacker) + a full-HP target, both with empty buffs.
    Returns the target's token id."""
    caster_tok = f"tok_hitrider_caster_{caster['id']}"
    target_tok = f"tok_hitrider_tgt_{target['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": caster_tok, "char_id": caster["id"], "name": caster["name"],
                 "initiative": 15, "hp_current": 40, "hp_max": 40, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": target_tok, "char_id": target["id"], "name": target["name"],
                 "initiative": 8, "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return target_tok


async def test_weapon_hit_rider_buffs_present_in_catalog():
    """Catalog anchor for the catalog-backed weapon-hit riders (Hunter's
    Mark). Hex is PHB-only (`catalog=False`) and intentionally not in the
    open SRD JSON layer, so it's excluded here but still gated behaviourally.
    """
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    catalog_slugs = [s for s, spec in _HIT_RIDER_BUFFS.items() if spec["catalog"]]
    assert catalog_slugs, "expected at least one catalog-backed weapon-hit rider"
    missing = [slug for slug in catalog_slugs if slug not in by_slug]
    assert not missing, f"weapon-hit-rider spells absent from catalog: {missing}"


async def test_weapon_hit_riders_apply_exact_bonus_damage(gm_client, roster):
    """For Hunter's Mark and Hex: real-cast the rider on a target, then have
    the caster attack that target and assert the `auto_uplifts` entry sourced
    from the buff carries exactly a `1d6` expression, an in-band roll that
    matches its own breakdown + total, and the registry damage type.

    The rider is rolled server-side per /attack; a dice seed pins the value so
    the breakdown/total cross-check is stable. A registry edit that changes
    the die (`1d6`→`1d8`), drops the rider, or retypes Hex away from necrotic
    moves the assertion and fails here.
    """
    target = roster[_HIT_RIDER_TARGET]
    failures: list[str] = []
    checked = 0
    try:
        for slug, spec in _HIT_RIDER_BUFFS.items():
            seed = 53000 + checked
            caster = roster[spec["caster"]]

            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/rest",
                json={"type": "long"},
            )
            target_tok = await _rider_seed_battle(gm_client, caster, target)

            body = {
                "character_id": caster["id"],
                "target_character_id": target["id"],
                "slot_level": 1, "override": True, "override_range": True,
            }
            body.update(spec["body_extra"])
            cast = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/{spec['endpoint']}", json=body,
            )
            if cast.status_code != 200:
                failures.append(f"{slug}: cast HTTP {cast.status_code} {cast.text[:120]}")
                continue
            rider_target = cast.json().get("target_combatant_id") or target_tok

            await _seed_dice(gm_client, seed)
            atk = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": caster["id"], "attack_index": 0,
                    "target_combatant_id": rider_target,
                    "target_character_id": target["id"], "target_name": target["name"],
                    "override": True, "override_range": True,
                },
            )
            if atk.status_code != 200:
                failures.append(f"{slug}: attack HTTP {atk.status_code} {atk.text[:120]}")
                continue
            ups = [u for u in (atk.json().get("auto_uplifts") or [])
                   if u.get("source") == spec["key"]]
            if len(ups) != 1:
                failures.append(
                    f"{slug}: expected exactly one '{spec['key']}' uplift, got "
                    f"{[u.get('source') for u in (atk.json().get('auto_uplifts') or [])]}"
                )
                continue
            u = ups[0]
            if u.get("expression") != spec["die"]:
                failures.append(f"{slug}: rider expression {u.get('expression')!r} != {spec['die']!r}")
            m = _HIT_RIDER_TOKEN.search(u.get("breakdown") or "")
            if not m:
                failures.append(f"{slug}: no 1d6 token in rider breakdown {u.get('breakdown')!r}")
                continue
            rolled, sub = int(m.group(1)), int(m.group(2))
            if not (1 <= rolled <= 6):
                failures.append(f"{slug}: rider d6 roll {rolled} out of [1,6] ({u.get('breakdown')!r})")
            if rolled != sub:
                failures.append(f"{slug}: rider d6 token {rolled} != subtotal {sub} ({u.get('breakdown')!r})")
            if int(u.get("total") or 0) != rolled:
                failures.append(f"{slug}: rider total {u.get('total')} != rolled die {rolled}")
            dt = (u.get("damage_type") or "").strip()
            if spec["damage_type"] is None:
                if not dt:
                    failures.append(f"{slug}: rider damage_type is empty (expected weapon type)")
            elif dt != spec["damage_type"]:
                failures.append(f"{slug}: rider damage_type {dt!r} != {spec['damage_type']!r}")
            checked += 1
    finally:
        await _seed_dice(gm_client, None)

    assert checked == len(_HIT_RIDER_BUFFS), (
        f"only exercised {checked}/{len(_HIT_RIDER_BUFFS)} weapon-hit-rider buffs"
    )
    assert not failures, (
        f"{len(failures)} weapon-hit-rider failures:\n  " + "\n  ".join(failures)
    )


# --- Phase 3e: movement-speed riders ----------------------------------------

# Haste (×2 speed) and Slow (½ speed) are the two buffs whose mechanical
# effect lands on the *movement* engine rather than the attack/save/AC paths.
# Both install an `effects` key the v2.99.98 `_effective_speed_walk` engine
# reads at /token/move time: Haste → `speed_multiplier: 2`, Slow →
# `speed_reduction_ft: base // 2` (rounded down to the nearest 5 ft). The gate
# real-casts each onto an *active mover* that owns a real map token, then drives
# a move that overshoots the post-buff cap and asserts the 409 `over_speed_cap`
# response's `cap_ft` equals the registry-derived effective speed exactly.
#
# Why this is the right surface: the move-cap reads the combatant's seeded
# `speed_walk`, so the test pins a known base (Haste 15 → cap 30, Slow 30 →
# cap 15) and the 409's `cap_ft` is the *only* free variable. A registry edit
# that retunes Haste's multiplier or Slow's halving — or drops either hook —
# moves `cap_ft` (or flips the 409 to a 200) and fails here. Mirrors the
# `test_token_move_speed_cap.py` parking + seed pattern, but the buff arrives
# via a real cast (Haste through /cast_spell + the scratch-inject, Slow through
# the dedicated /cast_slow) instead of a synthetic PUT-/battle buff.
_SPEED_RIDER_BUFFS = {
    "haste": {
        "mechanism": "cast_spell", "base_speed": 15, "expected_cap": 30,
        "move_x": 840.0, "move_ft": 35,
    },
    "slow": {
        "mechanism": "cast_slow", "base_speed": 30, "expected_cap": 15,
        "move_x": 630.0, "move_ft": 20,
    },
}

_SPEED_CASTER = "Thalindra Moonwhisper"
_SPEED_CASTER_CLASS = "wizard"
_SPEED_MOVER = "Pip Quickfingers"


async def _speed_tokens_by_char(gm_client) -> dict[int, dict]:
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    return {t["character_id"]: t for t in resp.json()["tokens"] if t.get("character_id")}


async def _speed_park(gm_client, token_id, x=350.0, y=350.0) -> None:
    """Park the mover's real token at a known origin, bypassing any stale
    over-speed / OA gate so the subsequent seeded move starts clean."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json={"x": x, "y": y, "over_speed_confirmed": True, "oa_confirmed": True},
    )


async def _speed_seed_battle(gm_client, mover, mover_token_id, caster, base_speed) -> str:
    """Active battle: the mover (active combatant, real map token, given base
    speed) + the caster. Returns the mover's combatant id (the cast target)."""
    mover_tok = f"tok_speedrider_mover_{mover['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": mover_tok, "char_id": mover["id"], "name": mover["name"],
                 "source_token_id": mover_token_id, "initiative": 20,
                 "hp_current": 40, "hp_max": 40, "speed_walk": base_speed, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False,
                             "movement": 0, "dash_bonus_ft": 0}},
                {"id": f"tok_speedrider_caster_{caster['id']}", "char_id": caster["id"],
                 "name": caster["name"], "initiative": 5, "hp_current": 30, "hp_max": 30,
                 "buffs": [], "economy": {"action": False, "bonus": False,
                                          "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return mover_tok


async def test_speed_rider_buffs_present_in_catalog():
    """Catalog anchor for the movement-speed riders (Haste + Slow). Both are
    open-SRD spells, so a rename/removal of either trips this gate."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    missing = [slug for slug in _SPEED_RIDER_BUFFS if slug not in by_slug]
    assert not missing, f"speed-rider spells absent from catalog: {missing}"


async def test_speed_rider_spells_apply_exact_move_cap(gm_client, roster):
    """For Haste (×2) and Slow (½): real-cast the rider onto an active mover,
    then drive a move that overshoots the post-buff cap and assert the 409
    `over_speed_cap` response's `cap_ft` equals the registry-derived effective
    speed exactly (Haste base 15 → 30; Slow base 30 → 15).

    The mover's seeded `speed_walk` is the only baseline input, so `cap_ft` is
    a pure function of the spell's registry effect. A multiplier/halving retune
    or a dropped hook moves `cap_ft` (or flips the 409 to a 200) and fails.
    """
    caster = roster[_SPEED_CASTER]
    mover = roster[_SPEED_MOVER]
    cid = caster["id"]

    tokens = await _speed_tokens_by_char(gm_client)
    assert mover["id"] in tokens, f"{_SPEED_MOVER} has no real map token"
    mover_token_id = tokens[mover["id"]]["id"]

    snap = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json")
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

    failures: list[str] = []
    checked = 0
    try:
        for slug, spec in _SPEED_RIDER_BUFFS.items():
            await _speed_park(gm_client, mover_token_id)
            mover_tok = await _speed_seed_battle(
                gm_client, mover, mover_token_id, caster, spec["base_speed"],
            )

            if spec["mechanism"] == "cast_spell":
                idx = idx_by_slug.get(slug)
                spell = by_slug.get(slug)
                if idx is None or spell is None:
                    failures.append(f"{slug}: not in catalog")
                    continue
                cast = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                    json={
                        "character_id": cid, "spell_index": idx,
                        "slot_level": int(spell.get("level_int") or 1) or 1,
                        "class_slug": _SPEED_CASTER_CLASS,
                        "target_character_id": mover["id"],
                        "target_combatant_id": mover_tok,
                        "target_name": mover["name"],
                        "override": True, "override_range": True,
                    },
                )
            else:  # cast_slow
                cast = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
                    json={
                        "character_id": cid, "class_slug": _SPEED_CASTER_CLASS,
                        "slot_level": 3, "target_combatant_ids": [mover_tok],
                        "override": True,
                    },
                )
            if cast.status_code != 200:
                failures.append(f"{slug}: cast HTTP {cast.status_code} {cast.text[:120]}")
                continue

            move = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/token/{mover_token_id}/move",
                json={"x": spec["move_x"], "y": 350.0},
            )
            if move.status_code != 409:
                failures.append(
                    f"{slug}: expected 409 over_speed_cap on a {spec['move_ft']} ft "
                    f"move vs the post-buff cap, got HTTP {move.status_code} "
                    f"{move.text[:160]}"
                )
                continue
            data = move.json()
            if data.get("error") != "over_speed_cap":
                failures.append(f"{slug}: 409 error {data.get('error')!r} != 'over_speed_cap'")
                continue
            if data.get("cap_ft") != spec["expected_cap"]:
                failures.append(
                    f"{slug}: cap_ft {data.get('cap_ft')} != expected "
                    f"{spec['expected_cap']} (base {spec['base_speed']}); full {data}"
                )
            checked += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
        )

    assert checked == len(_SPEED_RIDER_BUFFS), (
        f"only exercised {checked}/{len(_SPEED_RIDER_BUFFS)} speed-rider buffs"
    )
    assert not failures, (
        f"{len(failures)} speed-rider failures:\n  " + "\n  ".join(failures)
    )
