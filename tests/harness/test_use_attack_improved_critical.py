"""/api/campaign/{cid}/attack — Champion Fighter Improved Critical (Lv 3+).

v2.49.231: Champion Fighter Lv 3+ crits on 19 or 20 instead of just 20.
The server-side crit-detection block in `use_attack` reads the
`_attacker_crit_threshold(sheet)` helper to pick 19 or 20 depending on
the attacker's class/subclass/level.

Test strategy:
  - Seed `/api/test/dice/seed` with a fixed value so attack rolls are
    deterministic. Fire many attacks with Garrik (Lv 7 Champion Fighter post-v2.49.237 bump)
    and Pip (Lv 5 Rogue — control), parse the `attack_breakdown` to
    extract the kept d20 value, and assert the is_crit flag matches the
    expected per-class threshold.
  - The test doesn't rely on a SPECIFIC seed producing a SPECIFIC value
    — it iterates many seeds + rolls and groups assertions by
    "d20 kept value." Any roll of 19 by Garrik must crit; any roll of
    19 by Pip must NOT crit; any roll of 20 by either must crit.

Tests:
  - Garrik d20=19 → is_crit=True (Improved Critical fires)
  - Pip d20=19 → is_crit=False (regression guard — non-Champion stays at 20)
  - Both d20=20 → is_crit=True (baseline crit detection unchanged)
"""
from __future__ import annotations

import re

from .conftest import CAMPAIGN_ID


_D20_RE = re.compile(r"\d*d20[^d=+ ]*=(\d+)", re.IGNORECASE)


def _kept_d20(attack_breakdown: str) -> int | None:
    """Return the kept d20 value from an attack breakdown, or None
    when the breakdown is empty / unparseable.

    Matches the same regex the server-side crit-detection block uses,
    so the test parses the breakdown the same way the production code
    decides crit.
    """
    if not attack_breakdown:
        return None
    m = _D20_RE.search(attack_breakdown)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


async def _seed_battle(gm_client, char_id, name, target_char_id, target_name):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_{char_id}",
                    "char_id": char_id,
                    "name": name,
                    "initiative": 10,
                    "hp_current": 40, "hp_max": 40,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_{target_char_id}",
                    "char_id": target_char_id,
                    "name": target_name,
                    "initiative": 8,
                    "hp_current": 30, "hp_max": 30,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _drive_attacks(gm_client, attacker, target):
    """Fire 200 attacks with seeded dice. Returns a list of
    (kept_d20, is_crit) tuples — caller groups them by d20 value to
    assert the threshold behavior.

    Re-seeds before each batch so the test is reproducible against the
    same harness fixture. 200 swings at d20-uniform is enough to see
    every value 1-20 multiple times — the test asserts on the
    SHAPE of the distribution (is_crit reflects threshold), not on a
    specific roll count.
    """
    target_cid = f"tok_{target['id']}"
    results = []
    await gm_client.post("/api/test/dice/seed", json={"seed": 4321})
    try:
        for _ in range(200):
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": attacker["id"],
                    "attack_index": 0,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            d20 = _kept_d20(data.get("attack_breakdown") or "")
            if d20 is None:
                continue
            results.append((d20, bool(data.get("is_crit"))))
    finally:
        # Restore non-deterministic mode so subsequent tests aren't
        # poisoned by our seeded sequence. test_seed_endpoint_accepts_null_seed
        # already verifies this re-seed path works.
        await gm_client.post("/api/test/dice/seed", json={"seed": None})
    return results


async def test_champion_crits_on_19(gm_client, roster):
    """Garrik (Lv 7 Champion Fighter) — every d20 kept value of 19 in
    the rolled distribution must produce is_crit=True. Every d20 of 20
    likewise. d20 ≤ 18 must produce is_crit=False (regression guard).
    """
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, garrik["id"], garrik["name"], pip["id"], pip["name"])
    results = await _drive_attacks(gm_client, garrik, pip)
    nineteens = [crit for d20, crit in results if d20 == 19]
    twenties = [crit for d20, crit in results if d20 == 20]
    sub_19 = [crit for d20, crit in results if d20 < 19]
    # Statistical sanity — 200 rolls should yield ≥1 of each.
    assert nineteens, f"expected at least one d20=19 in 200 rolls; got distribution {sorted({d for d, _ in results})}"
    assert twenties, "expected at least one d20=20 in 200 rolls"
    assert sub_19, "expected at least one d20<19 in 200 rolls"
    # Improved Critical: every 19 must crit.
    assert all(nineteens), f"Garrik d20=19 should always crit (Improved Critical); got {nineteens}"
    # Baseline: every 20 must crit (regression guard).
    assert all(twenties), f"d20=20 should always crit; got {twenties}"
    # Non-crit baseline: no roll <19 should ever crit.
    assert not any(sub_19), f"d20<19 should never crit for Garrik; got {sub_19}"


async def test_rogue_does_not_crit_on_19(gm_client, roster):
    """Pip (Lv 5 Rogue) — control case. Improved Critical is Champion-
    only; Pip rolling 19 must NOT crit. d20=20 still crits per baseline.
    """
    pip = roster["Pip Quickfingers"]
    garrik = roster["Garrik Ironside"]
    await _seed_battle(gm_client, pip["id"], pip["name"], garrik["id"], garrik["name"])
    results = await _drive_attacks(gm_client, pip, garrik)
    nineteens = [crit for d20, crit in results if d20 == 19]
    twenties = [crit for d20, crit in results if d20 == 20]
    assert nineteens, "expected at least one d20=19 in 200 rolls"
    assert twenties, "expected at least one d20=20 in 200 rolls"
    # Regression guard: Rogue at 19 must not crit.
    assert not any(nineteens), (
        f"Pip (Rogue) d20=19 should NOT crit — only Champion Fighter Lv 3+ gets "
        f"Improved Critical. Got crits: {nineteens}"
    )
    # Baseline: nat-20 still crits.
    assert all(twenties), f"d20=20 should always crit; got {twenties}"
