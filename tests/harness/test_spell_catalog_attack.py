"""Phase 2C — spell-attack-roll assertions across the spell catalog.

For every spell ``/cast_spell`` resolves as a spell-attack roll (an
``attack_roll`` flag and no ``save_ability`` — Fire Bolt, Eldritch
Blast, Guiding Bolt, …): cast it at an NPC target and assert two
contracts, both content-drift gates.

  - **Attack bonus** — the engine rolls ``1d20 + (prof + spellcasting
    mod)``. The bonus isn't a standalone response field, so we derive
    it from ``auto_attack_total`` minus the natural d20 (parsed out of
    ``auto_attack_breakdown``'s ``[N]``) and assert it equals the RAW
    formula, uniform across every attack spell the caster throws.
  - **Hit/miss logic** — ``auto_attack_hit`` must follow the d20 rules:
    nat 20 always hits, nat 1 always misses, otherwise hit iff
    ``total >= target AC``. A content/engine edit that inverts the
    comparison or drops the crit/fumble special-casing is caught here.

Crit-doubling ("a critical hit doubles the damage dice") is asserted
separately and deterministically via the ``/api/test/dice/seed``
TEST_MODE endpoint — a random catalog loop can't reliably roll a nat
20, so the looping test above leaves crit-doubling to
``test_attack_crit_doubles_damage_dice`` below, which seeds the RNG
until Fire Bolt crits and asserts the damage breakdown shows the
doubled dice count (2d10 → 4d10).

Same scaffolding as ``test_spell_catalog_save.py`` (Phase 2B): one
test patches a scratch caster with the whole catalog + abundant slots,
seeds one NPC target, and loops the attack-spell subset — paying the
autouse ``clean_pcs`` long-rest once instead of per parameterized case.
"""
from __future__ import annotations

import re

from .conftest import CAMPAIGN_ID
from .spell_catalog import dice_range, is_attack_spell, load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_ABILITIES = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}

# Natural-d20 extractor: the engine's breakdown looks like
# ``1d20[4]=4 4  =>  8`` (the bracketed number is the raw die).
_NAT_RE = re.compile(r"\[(\d+)\]")

# Attack spells the catalog test can't yet assert cleanly. Empty today;
# add a slug -> reason here if a spell surfaces a known engine/content
# gap rather than silently dropping it (plan design principle #5).
_SKIP_SLUGS: dict[str, str] = {}


def _expected_attack_bonus(sheet: dict) -> int:
    """Caster's spell-attack bonus = ``proficiency + spellcasting mod``,
    replicating the endpoint (``tabletop_routes.py`` ~line 19215) incl.
    the WIS fallback when ``spellcasting_ability`` is unset on the demo
    sheet. (Equals the spell save DC minus 8.)"""
    prof = int(sheet.get("proficiency_bonus") or 2)
    spc = (sheet.get("spellcasting_ability") or "").strip().upper()[:3]
    if spc not in _ABILITIES:
        spc = "WIS"
    ability_score = int((sheet.get("abilities") or {}).get(spc, 10))
    mod = (ability_score - 10) // 2
    return prof + mod


def _all_entries(spells: list[dict]) -> list[dict]:
    """Minimal sheet entries for every catalog spell (for the bulk
    inject), so the attack subset can be cast by index."""
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


def _nat_d20(breakdown: str) -> int | None:
    m = _NAT_RE.search(breakdown or "")
    return int(m.group(1)) if m else None


async def _seed_bandit(gm_client) -> str:
    """Seed one very-high-HP NPC bandit so the attack spells in a row
    don't drop it (a dead combatant could stop resolving)."""
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    cid = "tok_atkcatalog_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cid, "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Attack Catalog Target",
                "initiative": 5, "hp_current": 999999, "hp_max": 999999,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return cid


async def test_every_attack_spell_bonus_and_hit(gm_client, roster):
    """Cast every spell-attack-roll catalog spell at an NPC and assert
    the derived attack bonus matches the caster's spell-attack bonus
    (uniform across all spells) and the hit verdict follows the d20
    rules vs the target AC."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}
    expected_bonus = _expected_attack_bonus(sheet)

    spells = load_all_spells()
    entries = _all_entries(spells)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    attack_spells = [
        s for s in spells
        if (s.get("slug") or "") not in _SKIP_SLUGS and is_attack_spell(s)
    ]

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    bonus_mismatches: list[str] = []
    hit_mismatches: list[str] = []
    unrolled: list[str] = []
    asserted = 0
    try:
        target_id = await _seed_bandit(gm_client)
        for s in attack_spells:
            slug = s["slug"]
            idx = idx_by_slug.get(slug)
            if idx is None:
                continue
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": int(s.get("level_int") or 0),
                    "class_slug": _SCRATCH_CLASS,
                    "target_combatant_id": target_id,
                    "target_name": "Attack Catalog Target",
                    "override": True,
                },
            )
            if resp.status_code != 200:
                unrolled.append(f"{slug}: HTTP {resp.status_code} {resp.text[:120]}")
                continue
            data = resp.json()
            breakdown = data.get("auto_attack_breakdown") or ""
            nat = _nat_d20(breakdown)
            if nat is None:
                # No attack roll surfaced (e.g. a summon spell that
                # didn't resolve to-hit). Record + skip rather than
                # asserting on absent fields.
                unrolled.append(f"{slug}: no [d20] in breakdown {breakdown!r}")
                continue
            total = int(data.get("auto_attack_total") or 0)
            ac = int(data.get("auto_attack_target_ac") or 0)
            got_hit = bool(data.get("auto_attack_hit"))

            derived_bonus = total - nat
            if derived_bonus != expected_bonus:
                bonus_mismatches.append(
                    f"{slug}: derived attack bonus {derived_bonus:+d} "
                    f"(total {total} - nat {nat}) != expected {expected_bonus:+d}"
                )
            expected_hit = (nat == 20) or (nat != 1 and total >= ac)
            if got_hit != expected_hit:
                hit_mismatches.append(
                    f"{slug}: auto_attack_hit {got_hit} != expected {expected_hit} "
                    f"(nat {nat}, total {total}, AC {ac})"
                )
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= 12, (
        f"only asserted {asserted} attack spells (expected ~15); "
        f"unrolled={unrolled}"
    )
    assert not bonus_mismatches, (
        f"{len(bonus_mismatches)} attack-bonus mismatches (expected uniform "
        f"{expected_bonus:+d}):\n  " + "\n  ".join(bonus_mismatches)
    )
    assert not hit_mismatches, (
        f"{len(hit_mismatches)} hit/miss-logic mismatches:\n  "
        + "\n  ".join(hit_mismatches)
    )


async def test_attack_crit_doubles_damage_dice(gm_client, roster):
    """A natural 20 doubles the damage dice (RAW PHB p.196). Seed the
    RNG until Fire Bolt crits, then assert the damage breakdown shows
    the doubled dice count (Fire Bolt at Wizard L5 is 2d10 → 4d10 on a
    crit) and the rolled damage stays inside the doubled-dice range."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}
    expected_bonus = _expected_attack_bonus(sheet)

    entries = [{
        "name": "Fire Bolt", "_slug": "fire-bolt", "level": 0,
        "class": _SCRATCH_CLASS, "prepared": True, "casting_time": "1 action",
    }]
    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    crit = None
    try:
        target_id = await _seed_bandit(gm_client)
        # Find a seed that makes Fire Bolt crit. Seed → cast with nothing
        # else drawing from the RNG in between, so the outcome is
        # deterministic per seed. Seed 5 crits today; the loop keeps the
        # test robust to engine RNG draw-order drift.
        for s in range(1, 80):
            await gm_client.post("/api/test/dice/seed", json={"seed": s})
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": 0,
                    "slot_level": 0,
                    "class_slug": _SCRATCH_CLASS,
                    "target_combatant_id": target_id,
                    "target_name": "Attack Catalog Target",
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if data.get("auto_attack_crit"):
                crit = data
                break
    finally:
        await gm_client.post("/api/test/dice/seed", json={"seed": None})
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert crit is not None, "no Fire Bolt crit found in 79 seeds"
    assert crit.get("auto_attack_hit") is True, "a crit must register as a hit"

    nat = _nat_d20(crit.get("auto_attack_breakdown") or "")
    assert nat == 20, f"crit breakdown should show nat 20, got {nat!r}"
    derived_bonus = int(crit.get("auto_attack_total") or 0) - nat
    assert derived_bonus == expected_bonus, (
        f"crit attack bonus {derived_bonus:+d} != expected {expected_bonus:+d}"
    )

    dmg_breakdown = crit.get("auto_attack_damage_breakdown") or ""
    # Fire Bolt at L5 is 2d10; a crit doubles the dice to 4d10. The
    # breakdown must show the DOUBLED count — the structural proof of
    # crit-doubling that a range check alone can't give.
    assert "4d10" in dmg_breakdown, (
        f"crit damage breakdown should show doubled 4d10, got {dmg_breakdown!r}"
    )
    lo, hi = dice_range("4d10")
    rolled = int(crit.get("auto_attack_damage_rolled") or 0)
    assert lo <= rolled <= hi, (
        f"crit damage {rolled} outside doubled range [{lo}, {hi}] — {dmg_breakdown!r}"
    )


async def test_attack_catalog_subset_nonempty():
    """Guard: the attack subset is substantial so the catalog test can't
    pass vacuously if the JSON's attack_roll flags go missing."""
    spells = load_all_spells()
    attack_spells = [s for s in spells if is_attack_spell(s)]
    assert len(attack_spells) >= 12, (
        f"expected ~15 attack-roll spells, found {len(attack_spells)} — the "
        f"catalog's attack_roll flags may have regressed."
    )
