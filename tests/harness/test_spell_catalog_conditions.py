"""Phase 2F-2 — save-gated condition installs (`_SPELL_CONDITION_MAP`).

Phase 2F (`test_spell_catalog_buff_install.py`) covered the *no-save*
buff installs in `_SPELL_BUFF_MAP` (Bless, Aid, Haste …): those land
unconditionally, so the test is deterministic. This file closes the
filed Phase 2F-2 follow-up — the **save-gated** condition installs in
`_SPELL_CONDITION_MAP` (Hold Person → Paralyzed, Bane → Baned, …),
which only install when the target *fails* its save.

The contract under test is `/cast_spell`'s single-target NPC
save-or-suck path (tabletop_routes.py ~line 20438): a no-damage spell
with a `save_ability`, cast at an NPC combatant, rolls the NPC's save
server-side, and **on a failure** looks the spell slug up in
`_SPELL_CONDITION_MAP` and installs the matching condition buff on the
target combatant — surfacing `auto_save_buff_key` / `auto_save_buff_name`
/ `auto_save_buff_duration` in the response.

To make a failure deterministic we seed the RNG (`/api/test/dice/seed`)
and loop seeds until the NPC's save lands below the caster's spell DC
(precedent: the attack-roll loops in `test_spell_catalog_exact_damage.py`).
For each spell we assert the response's buff key/name/duration match the
registry **and** the condition buff is actually present on the bandit
combatant's `buffs` list in the persisted battle state.

Scope — the 8 `_SPELL_CONDITION_MAP` entries that are genuine
single-target save-or-suck *spells*:
  Hold Person, Charm Person, Suggestion, Fear, Hideous Laughter,
  Confusion, Banishment, Bane.
Deliberately excluded:
  - `hold-monster` — its catalog `Cast` action carries no `save_ability`,
    so `/cast_spell` never rolls a save and the install path can't fire
    (a content gap the Phase 2G shape/Phase 2B save gates would surface,
    out of scope here).
  - `faerie-fire` — a 20-ft cube AoE in the catalog, so it routes through
    the `/place_aoe` pending-placement path (Phase 2G), not the
    single-target install path.
  - `stunning-strike` / `open-hand-prone` — Monk class-feature entries,
    not `/cast_spell` spells (covered by their dedicated endpoint tests).

Same scratch-caster bulk-inject scaffolding as the other Phase 2 files
(Thalindra the Wizard gets the whole catalog + abundant slots so every
condition spell is castable by index regardless of class legality).
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# slug -> expected install, mirroring `_SPELL_CONDITION_MAP`. `save` is
# the catalog action's save ability (used only by the guard test).
_CONDITION_SPELLS: dict[str, dict] = {
    "hold-person": {"key": "paralyzed", "name": "Paralyzed", "duration": 10, "save": "wis"},
    "charm-person": {"key": "charmed", "name": "Charmed", "duration": 600, "save": "wis"},
    "suggestion": {"key": "charmed", "name": "Charmed (Suggestion)", "duration": 4800, "save": "wis"},
    "fear": {"key": "frightened", "name": "Frightened", "duration": 10, "save": "wis"},
    "hideous-laughter": {"key": "incapacitated", "name": "Incapacitated (Laughing)", "duration": 10, "save": "wis"},
    "confusion": {"key": "confused", "name": "Confused", "duration": 10, "save": "wis"},
    "banishment": {"key": "banished", "name": "Banished", "duration": 10, "save": "cha"},
    "bane": {"key": "baned", "name": "Baned", "duration": 10, "save": "cha"},
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


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _bandit_template_id(gm_client) -> int:
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    return bandit["id"]


async def _seed_battle(gm_client, caster, tmpl_id, bandit_id):
    """Caster + a fresh, full-HP bandit NPC (buffs cleared) so each spell
    starts from a clean target."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_cond_caster_{caster['id']}", "char_id": caster["id"],
                 "name": caster["name"], "initiative": 20,
                 "hp_current": 30, "hp_max": 30, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": bandit_id, "char_id": None,
                 "token_template_id": tmpl_id, "name": "Condition Target",
                 "initiative": 1, "hp_current": 200, "hp_max": 200, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _combatant_buffs(gm_client, combatant_id) -> list[dict]:
    state = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json().get("battle") or {}
    for c in state.get("combatants") or []:
        if c.get("id") == combatant_id:
            return c.get("buffs") or []
    return []


async def test_every_condition_spell_installs_on_failed_save(gm_client, roster):
    """For each save-gated `_SPELL_CONDITION_MAP` spell, cast it at an NPC
    and force a failed save; assert the response surfaces the registry's
    buff key/name/duration AND the condition buff lands on the bandit
    combatant in the persisted battle state."""
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

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    failures: list[str] = []
    checked = 0
    try:
        tmpl_id = await _bandit_template_id(gm_client)
        bandit_id = "tok_cond_target"

        for slug, exp in _CONDITION_SPELLS.items():
            if slug not in idx_by_slug:
                failures.append(f"{slug}: not in catalog")
                continue
            # Cast at L3 so L1/L2 condition spells get a legal slot and
            # the higher-level ones (Confusion/Banishment L4 need L4) are
            # bumped per spell below.
            spell = next((s for s in spells if (s.get("slug") or "") == slug), {})
            slot = max(int(spell.get("level_int") or 1), 1)

            await _seed_battle(gm_client, caster, tmpl_id, bandit_id)

            failed_data = None
            for attempt in range(120):
                await _seed_dice(gm_client, 9000 + attempt)
                r = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                    json={
                        "character_id": cid,
                        "spell_index": idx_by_slug[slug],
                        "slot_level": slot,
                        "class_slug": _SCRATCH_CLASS,
                        "target_combatant_id": bandit_id,
                        "target_name": "Condition Target",
                        "override": True,
                    },
                )
                if r.status_code != 200:
                    failures.append(f"{slug}: HTTP {r.status_code} {r.text[:120]}")
                    break
                d = r.json()
                if d.get("auto_save_target_kind") != "npc":
                    failures.append(
                        f"{slug}: expected npc auto-save, got "
                        f"kind={d.get('auto_save_target_kind')!r} "
                        f"(no save rolled — content gap?)"
                    )
                    break
                if d.get("auto_save_passed") is False:
                    failed_data = d
                    break
            else:
                failures.append(f"{slug}: no failed save in 120 seeds")

            if failed_data is None:
                continue

            d = failed_data
            if d.get("auto_save_buff_key") != exp["key"]:
                failures.append(
                    f"{slug}: buff_key {d.get('auto_save_buff_key')!r} != {exp['key']!r}")
            if d.get("auto_save_buff_name") != exp["name"]:
                failures.append(
                    f"{slug}: buff_name {d.get('auto_save_buff_name')!r} != {exp['name']!r}")
            if int(d.get("auto_save_buff_duration") or 0) != exp["duration"]:
                failures.append(
                    f"{slug}: buff_duration {d.get('auto_save_buff_duration')!r} "
                    f"!= {exp['duration']}")

            buffs = await _combatant_buffs(gm_client, bandit_id)
            keys = {(b or {}).get("key") for b in buffs}
            if exp["key"] not in keys:
                failures.append(
                    f"{slug}: condition {exp['key']!r} not on bandit combatant; "
                    f"got keys={sorted(k for k in keys if k)}")
            else:
                installed = next(b for b in buffs if (b or {}).get("key") == exp["key"])
                if installed.get("source_char_id") != cid:
                    failures.append(
                        f"{slug}: installed buff source_char_id "
                        f"{installed.get('source_char_id')!r} != caster {cid}")
            checked += 1
    finally:
        await _seed_dice(gm_client, None)
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert checked == len(_CONDITION_SPELLS), (
        f"only verified {checked}/{len(_CONDITION_SPELLS)} condition installs"
    )
    assert not failures, (
        f"{len(failures)} condition-install failures:\n  " + "\n  ".join(failures)
    )


def test_condition_spells_present_with_save_and_no_damage_or_area():
    """Guard: every spell in `_CONDITION_SPELLS` is in the catalog as a
    no-damage, no-area single-target spell whose action carries the
    expected save ability — the preconditions the single-target install
    path depends on. Drift (a save dropped, a damage roll or AoE added)
    fails here before it can silently neuter the install gate above."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    problems: list[str] = []
    for slug, exp in _CONDITION_SPELLS.items():
        spell = by_slug.get(slug)
        if not spell:
            problems.append(f"{slug}: missing from catalog")
            continue
        acts = spell.get("actions") or []
        saves = {(a.get("save_ability") or "").lower() for a in acts}
        if exp["save"] not in saves:
            problems.append(f"{slug}: save {exp['save']!r} not in action saves {sorted(saves)}")
        if any(a.get("damage") for a in acts):
            problems.append(f"{slug}: has a damage roll (would skip the condition install)")
        if any((a.get("area") or {}).get("shape") for a in acts):
            problems.append(f"{slug}: has an AoE area (would route through /place_aoe)")
    assert not problems, "condition-spell precondition drift:\n  " + "\n  ".join(problems)
