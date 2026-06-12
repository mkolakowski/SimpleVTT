"""Phase 2A backfill — auto-hit damage assertions (Magic Missile).

The last of the three filed Phase 2A damage variants (after attack-roll
in v1, multi-beam in v2.182.8, save-for-half in v2.183.0). Magic Missile
is the catalog's one true auto-hit spell: its darts "automatically hit"
with no save and no attack roll (RAW PHB p.257). The engine rolls one
damage die *per target combatant id* in the cast body's
``target_combatant_ids`` list and surfaces them in ``auto_hit_targets``
(each: ``rolled`` / ``breakdown`` / ``damage_applied`` / ``damage_type``)
— but only when ``campaign.auto_apply_damage`` is on. So this test flips
that flag via the TEST_MODE ``/api/test/campaign/{id}/flags`` endpoint
(same as the save-for-half test), fires Magic Missile's 3 darts at an
NPC, and asserts each dart rolled in the ``1d4+1`` band with force type
and applied non-zero damage.

Note the server contract this gate covers: it's "one in-band roll per
target id sent", not dart-count scaling — the number of darts (3 base,
+1 per slot above 1st) is the *client's* responsibility (it sends N
ids), so the test sends 3 ids and asserts 3 in-band rolls. The other
catalog spells that technically match the no-save/no-attack/has-damage
predicate (Divine Favor, Spike Growth, Teleport mishap, …) are
situational damage, not targeted auto-hit attacks, so they're
deliberately out of scope here.

Same scratch-caster bulk-inject scaffolding as the other Phase 2 files.
Range-check only — exact-value assertion via the TEST_MODE dice seed is
the same filed Phase 2A.2 follow-up.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_assert import assert_damage_in_range
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_SLUG = "magic-missile"
_DARTS = 3          # base dart count at the natural (1st-level) slot
_PER_DART = "1d4+1"  # force damage per dart
_DTYPE = "force"


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
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    cid = "tok_autohit_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cid, "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Auto-hit Target",
                "initiative": 5, "hp_current": 999999, "hp_max": 999999,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return cid


async def test_magic_missile_autohit_rolls_each_dart(gm_client, roster):
    """With auto-apply on, fire Magic Missile's 3 darts at an NPC and
    assert each dart rolled in the 1d4+1 force band and applied damage."""
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
    idx = {e["_slug"]: i for i, e in enumerate(entries)}.get(_SLUG)
    assert idx is not None, f"{_SLUG} missing from catalog"

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    orig_flag = bool((await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )).json()["auto_apply_damage"])
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": True},
    )

    failures: list[str] = []
    try:
        target_id = await _seed_bandit(gm_client)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": cid,
                "spell_index": idx,
                "slot_level": 1,
                "class_slug": _SCRATCH_CLASS,
                "target_combatant_ids": [target_id] * _DARTS,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        darts = data.get("auto_hit_targets") or []
        if len(darts) != _DARTS:
            failures.append(f"fired {len(darts)} darts, expected {_DARTS}")
        for i, d in enumerate(darts):
            rolled = int(d.get("rolled") or 0)
            try:
                assert_damage_in_range(
                    rolled, _PER_DART, spell_name=f"{_SLUG} dart {i + 1}",
                )
            except AssertionError as exc:
                failures.append(str(exc))
            dtype = (d.get("damage_type") or "").strip().lower()
            if dtype != _DTYPE:
                failures.append(f"dart {i + 1}: type {dtype!r} != {_DTYPE!r}")
            if int(d.get("damage_applied") or 0) <= 0:
                failures.append(f"dart {i + 1}: damage_applied not > 0")
    finally:
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": orig_flag},
        )
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert not failures, (
        f"{len(failures)} Magic Missile auto-hit failures:\n  "
        + "\n  ".join(failures)
    )


def test_autohit_catalog_spell_present():
    """Guard: Magic Missile still carries a no-save, no-attack-roll
    force-damage action (the auto-hit shape this gate depends on)."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    spell = by_slug.get(_SLUG)
    assert spell, f"{_SLUG} absent from catalog"
    a = (spell.get("actions") or [{}])[0]
    assert a.get("damage"), f"{_SLUG}: lost its damage expression"
    assert not a.get("save_ability"), f"{_SLUG}: unexpectedly has a save"
    assert not a.get("attack_roll"), f"{_SLUG}: unexpectedly has an attack roll"
