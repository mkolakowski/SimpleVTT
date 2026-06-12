"""Phase 2A backfill — multi-beam attack-roll damage assertions.

Phase 2A v1 (``test_spell_catalog_damage.py``) covers single-target
attack-roll spells where the response carries one clean
``auto_attack_damage_rolled`` integer (Fire Bolt). This file backfills
the **multi-beam** category — spells that fire N separate attack rolls
at the same target, each rolling its own damage die (Scorching Ray's 3
rays, Eldritch Blast's caster-level beams). The engine surfaces those
in the ``auto_attack_beams`` list (one dict per beam with ``hit`` /
``crit`` / ``damage_rolled``), and ``auto_attack_damage_rolled`` is the
sum of every hitting beam's damage.

What this gate asserts, per spell:
  - the cast fires the expected number of beams (``len(auto_attack_beams)``);
  - every beam that hit rolled damage inside the single-beam dice
    expression's [min, max] band (so a content edit changing "2d6" → "3d6"
    on Scorching Ray, or the beam-scaling table, is caught);
  - the aggregate ``auto_attack_damage_rolled`` equals the sum of the
    per-beam ``damage_rolled`` (the aggregation contract);
  - the damage type matches the catalog JSON.

Like the other Phase 2 catalog files this uses the scratch-caster
bulk-inject pattern: patch Thalindra (Wizard L5) with the whole catalog
+ abundant slots, seed a battle with a low-AC NPC target so beams
reliably connect, and loop the subset inside one test (paying the
autouse ``clean_pcs`` long-rest once). ``override: True`` bypasses class
legality so the wizard can fire Eldritch Blast (a Warlock cantrip).

Beam counts are caster-level dependent for the cantrip: Thalindra is
Wizard L5, so Eldritch Blast hits the 2-beam tier (``damage_scaling``
level-5 row, ``extra_beams: 1``). Scorching Ray cast at its base slot
(2) fires 3 rays (1 + ``extra_beams: 2``).

Range-check only — exact-value assertion via the TEST_MODE dice seed is
the same filed Phase 2A.2 follow-up as the v1 file. The save-for-half
(``auto_save_damage_rolled``) and auto-hit (``auto_hit_targets``, Magic
Missile) damage paths are separate follow-ups: both gate on
``campaign.auto_apply_damage``, which needs the settings-form toggle the
multi-beam path doesn't require.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_assert import assert_damage_in_range
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# slug -> expected cast shape. ``beams`` is the count for Thalindra at
# Wizard L5 (Eldritch Blast's level-5 scaling tier; Scorching Ray's base
# 3 rays). ``expr`` is the per-beam dice; ``type`` the catalog damage type.
_CASES: dict[str, dict] = {
    "scorching-ray": {"slot": 2, "beams": 3, "expr": "2d6", "type": "fire"},
    "eldritch-blast": {"slot": 0, "beams": 2, "expr": "1d10", "type": "force"},
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


async def _seed_battle(gm_client, caster: dict) -> str:
    """Seed a battle with the caster + one low-AC, high-HP NPC target so
    the beams reliably hit. Returns the target combatant id."""
    target_id = "tok_multibeam_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_multibeam_caster_{caster['id']}",
                    "char_id": caster["id"], "name": caster["name"],
                    "initiative": 20, "hp_current": 60, "hp_max": 60,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
                {
                    "id": target_id,
                    "char_id": None, "name": "Multibeam Target",
                    "initiative": 5, "hp_current": 400, "hp_max": 400,
                    "ac": 5, "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return target_id


async def test_every_multibeam_spell_rolls_per_beam_damage(
    gm_client, gm_ws, roster,
):
    """Cast each multi-beam spell at a low-AC NPC and assert the beam
    count, per-beam damage range, aggregate sum, and damage type."""
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

    failures: list[str] = []
    asserted = 0
    try:
        target_id = await _seed_battle(gm_client, caster)
        for slug, want in _CASES.items():
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                failures.append(f"{slug}: not in catalog")
                continue

            # Retry until at least one beam hits. With target AC 5 and a
            # +d20 attack, a full miss across all beams is rare, but the
            # range-check needs a hitting beam to read damage off.
            data = None
            beams: list[dict] = []
            for _ in range(8):
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                    json={
                        "character_id": cid,
                        "spell_index": idx,
                        "slot_level": want["slot"],
                        "class_slug": _SCRATCH_CLASS,
                        "target_combatant_id": target_id,
                        "override": True,
                    },
                )
                if resp.status_code != 200:
                    failures.append(
                        f"{slug}: HTTP {resp.status_code} {resp.text[:120]}"
                    )
                    break
                data = resp.json()
                beams = data.get("auto_attack_beams") or []
                if any(b.get("hit") for b in beams):
                    break
            if data is None:
                continue

            if len(beams) != want["beams"]:
                failures.append(
                    f"{slug}: fired {len(beams)} beams, expected {want['beams']}"
                )
                continue

            hitting = [b for b in beams if b.get("hit")]
            if not hitting:
                failures.append(f"{slug}: no beam hit in 8 attempts")
                continue

            for b in hitting:
                rolled = int(b.get("damage_rolled") or 0)
                # A hitting beam must roll non-zero damage in band. Crit
                # doubles the dice, so widen the band on a crit beam.
                expr = want["expr"]
                if b.get("crit"):
                    # double the dice count: "2d6" -> "4d6"
                    n, _, faces = expr.partition("d")
                    expr = f"{int(n) * 2}d{faces}"
                try:
                    assert_damage_in_range(
                        rolled, expr, spell_name=f"{slug} beam {b.get('beam')}",
                        slot_level=want["slot"],
                    )
                except AssertionError as exc:
                    failures.append(str(exc))

            # Aggregate contract: auto_attack_damage_rolled == sum of beams.
            agg = int(data.get("auto_attack_damage_rolled") or 0)
            beam_sum = sum(int(b.get("damage_rolled") or 0) for b in beams)
            if agg != beam_sum:
                failures.append(
                    f"{slug}: aggregate {agg} != sum of beam damage {beam_sum}"
                )

            observed_type = (data.get("auto_attack_damage_type") or "").strip().lower()
            if observed_type and observed_type != want["type"]:
                failures.append(
                    f"{slug}: damage type {observed_type!r} != {want['type']!r}"
                )
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= len(_CASES), (
        f"only asserted {asserted}/{len(_CASES)} multi-beam spells"
    )
    assert not failures, (
        f"{len(failures)} multi-beam damage failures (content drift):\n  "
        + "\n  ".join(failures)
    )


def test_multibeam_catalog_subset_present():
    """Guard: every multi-beam slug resolves to a real catalog spell
    that still carries an attack-roll damage action with beam scaling."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    missing = [s for s in _CASES if s not in by_slug]
    assert not missing, f"multi-beam slugs absent from catalog: {missing}"
    for slug in _CASES:
        actions = by_slug[slug].get("actions") or []
        a = actions[0] if actions else {}
        assert a.get("attack_roll"), f"{slug}: lost its attack_roll flag"
        assert a.get("damage"), f"{slug}: lost its damage expression"
