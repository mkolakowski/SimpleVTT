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
and Bane (-1d4) — with an *exact* check rather than a "token appears"
check. The trick: roll the same attack twice under the same dice seed,
once with the buff on the attacker and once without. The d20 is the first
draw in both casts (identical seed → identical d20) and the flat attack
bonus is constant, so the only delta between the two attack totals is the
buff die. We then assert that delta equals exactly the d4 value the engine
prints in the buffed breakdown, with the registry-declared sign. A
regression that changes "1d4" → "1d6", drops the uplift, or flips the
sign moves the delta and fails here.

The buff is pre-seeded directly into the attacker's combatant payload via
PUT /battle — `_attacker_has_bless` / `_attacker_has_bane` read it straight
off the live combatant's `buffs` list — so the check is fully deterministic
with no save-fail loop. The catalog anchor (`test_*_present_in_catalog`)
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
