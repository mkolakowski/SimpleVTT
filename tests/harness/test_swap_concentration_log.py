"""🔁 GM log when a caster swaps concentration to a new spell.

v2.49.53 — closes the swap-replaced-by-new-cast follow-up filed in
v2.49.52. The audit set is now four-way:

  - 💔 = failed CON save (v2.39.0)
  - 💀 = incapacitated (v2.49.48 / .49 / .51)
  - ✋ = voluntary /end_buff (v2.49.52)
  - 🔁 = swapped to new concentration cast (this commit)

Mechanism: `_install_buff` already implements the RAW "one
concentration at a time" rule — installing a new concentration
buff drops any existing concentration buffs on the same combatant.
Pre-fix this happened silently (only the `buff_update` broadcast
carried `replaced_concentration` keys; no GM-visible audit log).
Fix emits a `type=roll` GM-only entry naming the old → new spell
when the replaced buff was an anchor the caster owned (source_char_id
absent or == self). The `not incapacitates_target` guard prevents
double-logging when the v2.49.51 💀 path is the real cause.

Test strategy: the demo doesn't expose two different concentration-
spell endpoints for any single PC (Hex is Warlock, Hunter's Mark
is Ranger, save-or-suck spells aren't all on one spell list). So
the tests seed an initial concentration buff onto the caster's
combatant via `/battle` PUT, then trigger `_install_buff` via
`/cast_hex` to exercise the swap path with a known-different key.

Tests:
  - Seed Magnus with a non-Hex concentration anchor; cast Hex →
    🔁 log fires naming old → Hex.
  - Seed Magnus with a non-own concentration buff (source=enemy);
    cast Hex → NO 🔁 log (the buff being dropped wasn't an
    anchor Magnus owned).
  - Cast Hex when Magnus has no prior concentration → NO 🔁 log
    (nothing replaced).
"""
import asyncio
import time
from typing import List

from .conftest import CAMPAIGN_ID


async def _seed_battle_with_buff(
    gm_client, magnus, pip, *, magnus_buffs: List[dict],
):
    """Seed Magnus + Pip in battle, with Magnus carrying ``magnus_buffs``."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_swap_{magnus['id']}",
                    "char_id": magnus["id"],
                    "name": magnus["name"],
                    "initiative": 10,
                    "hp_current": 30,
                    "hp_max": 30,
                    "buffs": magnus_buffs,
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_swap_{pip['id']}",
                    "char_id": pip["id"],
                    "name": pip["name"],
                    "initiative": 9,
                    "hp_current": 30,
                    "hp_max": 30,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


def _swap_logs(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("roll")
        if (m.get("data") or {}).get("visibility") == "gm_only"
        and "🔁" in ((m.get("data") or {}).get("note") or "")
    ]


async def _wait_for_swap_log(gm_ws, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hits = _swap_logs(gm_ws)
        if hits:
            return hits[0]
        await asyncio.sleep(0.02)
    return None


async def test_swap_own_anchor_emits_swap_log(gm_client, gm_ws, roster):
    """Magnus pre-carries an own-anchor concentration buff (key
    'concentration-bless', source=Magnus). Casting Hex (different key,
    also concentration) triggers the swap → 🔁 log fires naming
    Bless → Hex."""
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Pre-seed Magnus's combatant with a concentration anchor. Using
    # a key the demo doesn't recognize (concentration-bless) so the
    # swap target is unambiguous.
    seeded = {
        "key": "concentration-bless",
        "name": "Concentrating: Bless",
        "icon": "🌀",
        "source_char_id": magnus["id"],
        "concentration": True,
        "effects": ["Concentrating on Bless"],
    }
    await _seed_battle_with_buff(
        gm_client, magnus, pip, magnus_buffs=[seeded],
    )
    gm_ws.mark()

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text

    log = await _wait_for_swap_log(gm_ws)
    assert log is not None, (
        f"expected 🔁 GM log for Bless → Hex swap; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )
    note = log["data"]["note"]
    breakdown = log["data"]["breakdown"]
    assert note.startswith("🔁"), f"note should start with 🔁; got {note!r}"
    assert "bless" in note.lower(), f"old spell missing; got {note!r}"
    assert "hex" in note.lower(), f"new spell missing; got {note!r}"
    assert "swapped" in note.lower() or "→" in note, (
        f"note should describe the swap direction; got {note!r}"
    )
    assert "swap" in breakdown.lower() or "cast hex" in breakdown.lower(), (
        f"breakdown should describe the swap; got {breakdown!r}"
    )

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )


async def test_swap_paired_buff_does_not_emit_log(gm_client, gm_ws, roster):
    """Magnus carries a concentration buff sourced by an enemy (mimics
    Magnus being a Hold Person victim). Casting Hex — currently the
    swap loop drops the paired buff (separate pre-existing bug filed)
    — but the 🔁 log MUST NOT fire because Magnus wasn't actually
    concentrating on it.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    enemy_id = 99999  # not a real character; just a non-magnus marker
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    seeded_paired = {
        "key": "paralyzed",
        "name": "Paralyzed",
        "icon": "🥶",
        "source_char_id": enemy_id,
        "concentration": True,
        "effects": ["paired condition from enemy caster"],
    }
    await _seed_battle_with_buff(
        gm_client, magnus, pip, magnus_buffs=[seeded_paired],
    )
    gm_ws.mark()

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text

    # Wait briefly for any spurious broadcasts.
    await asyncio.sleep(0.5)
    swaps = _swap_logs(gm_ws)
    assert not swaps, (
        f"paired-buff swap should NOT emit 🔁 (victim wasn't concentrating); "
        f"got {[(m.get('data') or {}).get('note') for m in swaps]}"
    )

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )


async def test_no_prior_concentration_no_swap_log(gm_client, gm_ws, roster):
    """Casting Hex with no prior concentration on Magnus → just a
    fresh install. No 🔁 log (nothing was replaced)."""
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Clear any leftover concentration anchor from prior tests.
    for k in ("hex", "concentration-bless", "concentration-hold-person", "paralyzed"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    await _seed_battle_with_buff(
        gm_client, magnus, pip, magnus_buffs=[],
    )
    gm_ws.mark()

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text

    await asyncio.sleep(0.5)
    swaps = _swap_logs(gm_ws)
    assert not swaps, (
        f"fresh concentration install (no prior anchor) should NOT emit 🔁; "
        f"got {[(m.get('data') or {}).get('note') for m in swaps]}"
    )

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )
