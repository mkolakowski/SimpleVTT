"""v2.99.465 — data-invariant guard: every SRD monster attack-roll
action carries an `attack_bonus`.

Pure-Python test (no HTTP / WS harness fixtures); walks the shipped
`app/data/local/dnd5e/monsters/*.json` content layer directly.

Background — the P1 "NPCs unable to use action buttons (Vex's Dagger
Strike)" bug: every `attack_roll: true` action in the 322 local SRD
monster JSONs was missing `attack_bonus` (null), so the client's
strike handler (`hasAttackRoll = bonus && damage`) fell through to the
legacy `/roll` path instead of `/npc_attack` — the NPC strike resolved
no hit + no damage. v2.99.465 backfilled `attack_bonus` from each
action's `desc` ("+N to hit"). This test guards that invariant so a
future SRD rebuild that drops the field fails CI instead of silently
re-breaking every monster's Strike button.
"""
import glob
import json
import os
import re

_MONSTER_DIR = os.path.join("app", "data", "local", "dnd5e", "monsters")
_TO_HIT = re.compile(r"[+-]\d+\s+to hit", re.IGNORECASE)


def _attack_actions():
    """Yield (slug, action) for every attack_roll action in the SRD set."""
    for f in sorted(glob.glob(os.path.join(_MONSTER_DIR, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a malformed file is its own failure
            continue
        for a in d.get("actions", []) or []:
            if isinstance(a, dict) and a.get("attack_roll"):
                yield d.get("slug") or os.path.basename(f), a


def test_every_attack_roll_action_has_attack_bonus():
    """No `attack_roll: true` action may have a null/empty attack_bonus —
    that's exactly what broke every NPC Strike button pre-v2.99.465."""
    missing = [
        (slug, a.get("name"))
        for slug, a in _attack_actions()
        if a.get("attack_bonus") in (None, "", 0)
    ]
    assert not missing, (
        f"{len(missing)} attack-roll action(s) missing attack_bonus "
        f"(NPC Strike → /npc_attack breaks): {missing[:15]}"
    )


def test_attack_bonus_matches_desc_to_hit():
    """The backfilled attack_bonus matches the '+N to hit' in the desc
    (sanity that the parse, not a guess, populated it)."""
    mismatches = []
    for slug, a in _attack_actions():
        m = _TO_HIT.search(str(a.get("desc") or ""))
        if not m:
            continue
        desc_bonus = m.group(0).split()[0]  # "+5"
        if str(a.get("attack_bonus") or "").lstrip("+") != desc_bonus.lstrip("+"):
            mismatches.append((slug, a.get("name"),
                               a.get("attack_bonus"), desc_bonus))
    assert not mismatches, f"attack_bonus ≠ desc to-hit: {mismatches[:15]}"


def test_bandit_captain_dagger_is_plus5():
    """The exact case from the TODO bug report — Vex (Bandit Captain)'s
    Dagger Strike — now carries +5 to hit."""
    d = json.load(open(
        os.path.join(_MONSTER_DIR, "bandit-captain.json"), encoding="utf-8"))
    dagger = next(a for a in d["actions"] if a.get("name") == "Dagger")
    assert dagger["attack_bonus"] == "+5"
