"""Phase 2E — concentration assertions across the spell catalog.

For every concentration buff-spell the engine knows how to install
(``_SPELL_BUFF_MAP`` entries flagged ``concentration: True``): cast it
at a PC target in an active battle and assert two RAW contracts —

  - **Install marks concentration** — the buff lands on the target with
    ``concentration: True``. A content/registry edit that silently drops
    the concentration flag is caught here.
  - **One-at-a-time swap** — casting a second concentration spell from
    the same caster drops the prior anchor (RAW PHB p.203 "you lose
    concentration on the previous spell"). The drop is asserted both in
    the post-cast battle state AND in the ``buff_update`` broadcast's
    ``replaced_concentration`` list.

The concentration set mirrors the ``_SPELL_BUFF_MAP`` registry entries
flagged ``concentration: True`` (the code registry). It's listed
explicitly here because the harness runs against the docker container
over HTTP and can't import the fastapi-dependent route module locally.
For each of these the installed buff key equals the spell slug.

The JSON catalog's ``concentration`` field — historically an SRD-build
bug that shipped Bless / Moonbeam / Hold Person / ~125 others as
``concentration: false`` (the build script keyed off the literal word
"concentration" in the duration, missing the common "Up to N …" phrasing)
— was corrected in v2.568.1. ``test_concentration_flag_matches_duration``
below now gates the catalog data directly.

Same scratch-caster bulk-inject scaffolding as ``test_spell_catalog_
save.py`` (Phase 2B): one test patches the caster with the whole
catalog + abundant slots and loops the concentration subset, paying the
autouse ``clean_pcs`` long-rest once instead of per parameterized case.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_TARGET = "Krieger Stonefist"

# Buff-spell slugs the engine installs with the RAW concentration flag
# set (mirrors _SPELL_BUFF_MAP entries with concentration=True). The
# installed buff key equals the slug for every entry here. A new
# concentration buff-spell should be added to this list when registered.
_CONCENTRATION_SLUGS = sorted([
    "bless",
    "heroism",
    "shield-of-faith",
    "protection-from-evil-and-good",
    "haste",
])


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
    """Seed a battle with the caster + a PC target in init so
    ``_install_buff`` (which requires an active battle and the target in
    init) can land the concentration buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_conccat_caster_{caster['id']}",
                    "char_id": caster["id"], "name": caster["name"],
                    "initiative": 20, "hp_current": 60, "hp_max": 60,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False,
                                "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_conccat_target_{target['id']}",
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
    tgt = next(
        (c for c in combs if c.get("char_id") == target_char_id), {},
    )
    return [b for b in (tgt.get("buffs") or []) if isinstance(b, dict)]


async def test_every_concentration_spell_installs_and_swaps(
    gm_client, gm_ws, roster,
):
    """Self-cast each concentration buff-spell and assert it installs a
    concentration-flagged buff; then assert each subsequent cast drops
    the prior anchor (RAW one-at-a-time).

    The cast targets the caster herself so the buff lands on the caster's
    own combatant — that's where ``_install_buff``'s one-at-a-time swap
    loop fires (it keeps concentration buffs sourced by a *different*
    caster, which is the correct RAW behavior for buffs cast on others)."""
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

    install_failures: list[str] = []
    swap_failures: list[str] = []
    asserted = 0
    prev_key: str | None = None
    try:
        await _seed_battle(gm_client, caster, target)
        for slug in _CONCENTRATION_SLUGS:
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                install_failures.append(f"{slug}: not in catalog")
                continue
            expected_key = slug  # buff key == slug for every entry here

            gm_ws.mark()
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": int(spell.get("level_int") or 1) or 1,
                    "class_slug": _SCRATCH_CLASS,
                    "target_character_id": cid,
                    "target_name": caster["name"],
                    "override": True,
                },
            )
            if resp.status_code != 200:
                install_failures.append(
                    f"{slug}: HTTP {resp.status_code} {resp.text[:120]}"
                )
                continue

            # Every successful install broadcasts one buff_update — block
            # for it so the WS-side swap read below can't race the cast.
            await gm_ws.wait_for("buff_update", 3.0)
            buffs = await _target_buffs(gm_client, cid)
            anchor = next(
                (b for b in buffs if b.get("key") == expected_key), None,
            )
            if anchor is None:
                install_failures.append(
                    f"{slug}: buff {expected_key!r} not installed on caster"
                )
                continue
            if not anchor.get("concentration"):
                install_failures.append(
                    f"{slug}: installed buff missing concentration flag"
                )

            # Swap: the prior anchor must be gone from the target AND
            # reported in the buff_update broadcast's replaced list.
            if prev_key is not None:
                keys_now = {b.get("key") for b in buffs}
                if prev_key in keys_now:
                    swap_failures.append(
                        f"{slug}: prior anchor {prev_key!r} survived the swap"
                    )
                replaced = set()
                for msg in gm_ws.buffered("buff_update"):
                    replaced |= set(
                        (msg.get("data") or {}).get("replaced_concentration") or []
                    )
                if prev_key not in replaced:
                    swap_failures.append(
                        f"{slug}: broadcast replaced_concentration {sorted(replaced)} "
                        f"missing prior anchor {prev_key!r}"
                    )

            prev_key = expected_key
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= 4, (
        f"only asserted {asserted} concentration spells; expected >= 5 — "
        f"the _SPELL_BUFF_MAP concentration subset may have shrunk."
    )
    assert not install_failures, (
        f"{len(install_failures)} concentration-install failures:\n  "
        + "\n  ".join(install_failures)
    )
    assert not swap_failures, (
        f"{len(swap_failures)} concentration-swap failures (RAW one-at-a-time):\n  "
        + "\n  ".join(swap_failures)
    )


def test_concentration_catalog_subset_nonempty():
    """Guard: the concentration subset stays populated so the gate can't
    pass vacuously, and every slug resolves to a real catalog spell."""
    assert len(_CONCENTRATION_SLUGS) >= 5, (
        f"expected >= 5 concentration buff-spells, "
        f"found {len(_CONCENTRATION_SLUGS)}: {_CONCENTRATION_SLUGS}"
    )
    catalog_slugs = {(s.get("slug") or "") for s in load_all_spells()}
    missing = [s for s in _CONCENTRATION_SLUGS if s not in catalog_slugs]
    assert not missing, (
        f"concentration slugs absent from the spell catalog: {missing}"
    )


# ── v2.568.1 — JSON catalog concentration-flag correctness ───────────────────
def _implies_concentration(duration: str) -> bool:
    """5e's canonical concentration phrasing is a duration of "Up to N …";
    a few SRD entries also spell it out literally in the duration."""
    d = (duration or "").strip().lower()
    return d.startswith("up to") or "concentration" in d


def test_concentration_flag_matches_duration():
    """The catalog ``concentration`` flag matches each spell's duration in
    BOTH directions — the invariant the v2.568.1 build-script fix restored.
    A regression (the heuristic reverting to "concentration" in duration,
    which misses "Up to N …") trips the first assert."""
    spells = load_all_spells()
    assert spells, "no spells loaded from the catalog"
    wrong_false = sorted(
        s.get("slug") for s in spells
        if _implies_concentration(s.get("duration", ""))
        and not bool(s.get("concentration"))
    )
    wrong_true = sorted(
        s.get("slug") for s in spells
        if not _implies_concentration(s.get("duration", ""))
        and bool(s.get("concentration"))
    )
    assert not wrong_false, (
        f"{len(wrong_false)} spell(s) have a concentration duration but are "
        f"flagged concentration:false — the build-script heuristic regressed: "
        f"{wrong_false[:12]}"
    )
    assert not wrong_true, (
        f"{len(wrong_true)} spell(s) are flagged concentration:true but their "
        f"duration doesn't imply concentration: {wrong_true[:12]}"
    )


def test_known_concentration_spells_flagged():
    """Spot-check a sample of the spells corrected by v2.568.1 (each was
    ``concentration: false`` in the catalog before the fix)."""
    spells = {s.get("slug"): s for s in load_all_spells()}
    for slug in (
        "moonbeam", "bless", "hold-person", "fly", "haste", "web",
        "insect-plague", "cloudkill", "call-lightning", "hunters-mark",
    ):
        assert slug in spells, f"{slug} missing from the catalog"
        assert bool(spells[slug].get("concentration")), (
            f"{slug} should be flagged concentration:true after v2.568.1"
        )
