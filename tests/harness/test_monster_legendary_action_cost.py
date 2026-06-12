"""v2.159.33 — data-invariant guard: every SRD legendary action whose
name carries a "(Costs N Actions)" suffix has its `cost` integer set
to N (not the default 1).

Pure-Python test (no HTTP / WS harness fixtures); walks the shipped
`app/data/local/dnd5e/monsters/*.json` content layer directly.

Background — Phase 1a of `docs/plans/legendary-actions.md`. The SRD
text carries the legendary-action cost in the action name as
"(Costs N Actions)"; the shipped data layer originally had every
legendary action set to `cost: 1` regardless of suffix. v2.159.33
backfilled 39 cost integers across 30 monsters from the suffix.
This test guards that invariant so a future SRD rebuild that drops
the integer fails CI instead of silently re-breaking the
`/use_legendary_action` dispatch budget check (Phase 1b).

A legendary action with cost 2 must consume 2 of the per-round
3-point legendary-action budget; a cost 3 consumes all 3. Without
the integer set correctly, an ancient dragon's Wing Attack could
fire 3 times per round instead of once.
"""
import glob
import json
import os
import re

_MONSTER_DIR = os.path.join("app", "data", "local", "dnd5e", "monsters")
_COSTS_RE = re.compile(r"\(Costs (\d+) Actions?\)", re.IGNORECASE)


def _legendary_actions_with_cost_suffix():
    """Yield (slug, action, expected_cost) for every legendary_action
    whose name carries a "(Costs N Actions)" suffix."""
    for f in sorted(glob.glob(os.path.join(_MONSTER_DIR, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for a in d.get("actions", []) or []:
            if not isinstance(a, dict):
                continue
            if a.get("category") != "legendary_action":
                continue
            m = _COSTS_RE.search(a.get("name", ""))
            if not m:
                continue
            yield d.get("slug") or os.path.basename(f), a, int(m.group(1))


def test_every_costs_n_legendary_action_has_matching_cost_integer():
    """No legendary action with a "(Costs N Actions)" suffix may carry
    `cost != N`. That's exactly what would break the Phase 1b
    /use_legendary_action budget gate."""
    mismatched = [
        (slug, a.get("name"), a.get("cost"), expected)
        for slug, a, expected in _legendary_actions_with_cost_suffix()
        if a.get("cost") != expected
    ]
    assert not mismatched, (
        f"{len(mismatched)} legendary action(s) with cost suffix in name "
        f"but mismatched `cost` integer (Phase 1b budget gate breaks): "
        f"{mismatched[:10]}"
    )


def test_ancient_red_dragon_wing_attack_costs_2():
    """Spot-check the canonical ancient-red-dragon Wing Attack."""
    path = os.path.join(_MONSTER_DIR, "ancient-red-dragon.json")
    data = json.load(open(path, encoding="utf-8"))
    wing = next(
        a for a in data["actions"]
        if a.get("category") == "legendary_action"
        and "Wing Attack" in a.get("name", "")
    )
    assert wing["cost"] == 2, (
        f"Ancient Red Dragon Wing Attack cost should be 2, got {wing['cost']}"
    )


def test_lich_disrupt_life_costs_3():
    """Spot-check a cost-3 legendary action (the highest cost in SRD)."""
    path = os.path.join(_MONSTER_DIR, "lich.json")
    data = json.load(open(path, encoding="utf-8"))
    disrupt = next(
        a for a in data["actions"]
        if a.get("category") == "legendary_action"
        and "Disrupt Life" in a.get("name", "")
    )
    assert disrupt["cost"] == 3, (
        f"Lich Disrupt Life cost should be 3, got {disrupt['cost']}"
    )


def test_legendary_action_costs_in_valid_range():
    """Every legendary_action must carry `cost` in {1, 2, 3}. RAW SRD 5.1
    only uses costs 1, 2, or 3."""
    out_of_range = []
    for f in sorted(glob.glob(os.path.join(_MONSTER_DIR, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for a in d.get("actions", []) or []:
            if not isinstance(a, dict):
                continue
            if a.get("category") != "legendary_action":
                continue
            cost = a.get("cost")
            if cost not in (1, 2, 3):
                out_of_range.append(
                    (d.get("slug") or os.path.basename(f), a.get("name"), cost)
                )
    assert not out_of_range, (
        f"{len(out_of_range)} legendary action(s) with cost outside [1, 2, 3]: "
        f"{out_of_range[:10]}"
    )
