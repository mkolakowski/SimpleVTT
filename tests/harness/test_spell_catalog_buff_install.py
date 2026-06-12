"""Phase 2F — buff-install payload assertions across the spell catalog.

For every spell the engine installs as a persistent buff on a target
(the ``_SPELL_BUFF_MAP`` registry entries): cast it at a *separate* PC
target in an active battle and assert the installed buff's payload — its
``key``, ``name``, ``duration_rounds``, and ``concentration`` flag —
matches the expected RAW values. A content/registry edit that renames a
buff key (breaking the auto-uplift / intercept paths that look it up),
shortens a duration, or flips a concentration flag is caught here.

This complements Phase 2E (`test_spell_catalog_concentration.py`), which
*self-casts* the 5 concentration buffs to exercise the one-at-a-time
swap. Phase 2F casts on a *different* combatant — the cross-combatant
install path `_install_buff` takes when a caster buffs an ally — and
covers all 9 buff-map entries, including the 4 non-concentration buffs
(Aid, Sanctuary, Mage Armor, Longstrider) that 2E never touched. These
install unconditionally (no save gate), so the test is fully
deterministic.

The expected payloads mirror ``_SPELL_BUFF_MAP``; they're listed here
explicitly (rather than imported) because the harness runs against the
docker container over HTTP and can't import the fastapi route module
locally. The buff key equals the spell slug for every entry.

Same scratch-caster bulk-inject scaffolding as the other Phase 2 files:
one test patches the caster with the whole catalog + abundant slots and
loops the subset, paying the autouse ``clean_pcs`` long-rest once.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_TARGET = "Krieger Stonefist"

# slug -> expected installed-buff payload, mirroring _SPELL_BUFF_MAP.
# key == slug for every entry. A new buff-install spell joins this gate
# by adding a row here.
_EXPECTED: dict[str, dict] = {
    "bless": {"name": "Bless", "duration_rounds": 10, "concentration": True},
    "heroism": {"name": "Heroism", "duration_rounds": 10, "concentration": True},
    "shield-of-faith": {"name": "Shield of Faith", "duration_rounds": 100, "concentration": True},
    "aid": {"name": "Aid", "duration_rounds": 4800, "concentration": False},
    "sanctuary": {"name": "Sanctuary", "duration_rounds": 10, "concentration": False},
    "protection-from-evil-and-good": {"name": "Protection from Evil and Good", "duration_rounds": 100, "concentration": True},
    "mage-armor": {"name": "Mage Armor", "duration_rounds": 4800, "concentration": False},
    "haste": {"name": "Haste", "duration_rounds": 10, "concentration": True},
    "longstrider": {"name": "Longstrider", "duration_rounds": 600, "concentration": False},
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


async def _seed_battle(gm_client, caster: dict, target: dict) -> None:
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_buffcat_caster_{caster['id']}",
                    "char_id": caster["id"], "name": caster["name"],
                    "initiative": 20, "hp_current": 60, "hp_max": 60,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_buffcat_target_{target['id']}",
                    "char_id": target["id"], "name": target["name"],
                    "initiative": 10, "hp_current": 75, "hp_max": 75,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _target_buffs(gm_client, target_char_id: int) -> list[dict]:
    got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
    tgt = next((c for c in combs if c.get("char_id") == target_char_id), {})
    return [b for b in (tgt.get("buffs") or []) if isinstance(b, dict)]


async def test_every_buff_spell_installs_expected_payload(
    gm_client, gm_ws, roster,
):
    """Cast each buff-install spell at a separate PC target and assert
    the installed buff's key/name/duration_rounds/concentration match
    the expected RAW payload."""
    caster = roster[_SCRATCH_CASTER]
    target = roster[_TARGET]
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
        await _seed_battle(gm_client, caster, target)
        for slug, want in _EXPECTED.items():
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                failures.append(f"{slug}: not in catalog")
                continue

            gm_ws.mark()
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": int(spell.get("level_int") or 1) or 1,
                    "class_slug": _SCRATCH_CLASS,
                    "target_character_id": target["id"],
                    "target_name": target["name"],
                    "override": True,
                },
            )
            if resp.status_code != 200:
                failures.append(
                    f"{slug}: HTTP {resp.status_code} {resp.text[:120]}"
                )
                continue

            await gm_ws.wait_for("buff_update", 3.0)
            buffs = await _target_buffs(gm_client, target["id"])
            anchor = next((b for b in buffs if b.get("key") == slug), None)
            if anchor is None:
                failures.append(
                    f"{slug}: buff {slug!r} not installed on target; "
                    f"got keys {[b.get('key') for b in buffs]}"
                )
                continue
            if anchor.get("name") != want["name"]:
                failures.append(
                    f"{slug}: name {anchor.get('name')!r} != {want['name']!r}"
                )
            if anchor.get("duration_rounds") != want["duration_rounds"]:
                failures.append(
                    f"{slug}: duration_rounds {anchor.get('duration_rounds')!r} "
                    f"!= {want['duration_rounds']}"
                )
            if bool(anchor.get("concentration")) != want["concentration"]:
                failures.append(
                    f"{slug}: concentration {bool(anchor.get('concentration'))} "
                    f"!= {want['concentration']}"
                )
            if not anchor.get("effects"):
                failures.append(f"{slug}: installed buff has empty effects")
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= len(_EXPECTED), (
        f"only asserted {asserted}/{len(_EXPECTED)} buff spells; "
        f"the _SPELL_BUFF_MAP subset may have shrunk."
    )
    assert not failures, (
        f"{len(failures)} buff-install payload failures (content drift):\n  "
        + "\n  ".join(failures)
    )


def test_buff_install_catalog_subset_nonempty():
    """Guard: the buff-install subset stays populated and every slug
    resolves to a real catalog spell."""
    assert len(_EXPECTED) >= 9, (
        f"expected >= 9 buff-install spells, found {len(_EXPECTED)}"
    )
    catalog_slugs = {(s.get("slug") or "") for s in load_all_spells()}
    missing = [s for s in _EXPECTED if s not in catalog_slugs]
    assert not missing, (
        f"buff-install slugs absent from the spell catalog: {missing}"
    )
