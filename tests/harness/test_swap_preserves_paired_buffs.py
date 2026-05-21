"""Swap loop preserves paired condition buffs from other casters.

v2.49.54 — fixes the swap-loop bug filed in v2.49.53. RAW: the
"one concentration at a time" rule only applies to the combatant's
OWN concentration spells. A paired condition buff (e.g. Paralyzed
on a Hold Person victim, source = enemy caster) is sustained by
the SOURCE caster's concentration, not the victim's. The victim
casting a new concentration spell of their own shouldn't drop
the paired condition — that would let a victim "shake off" being
Held by simply casting Hex.

Pre-fix, `_install_buff`'s swap loop dropped EVERY `concentration:
True` buff on the combatant when a new concentration buff landed,
regardless of source. Fix: filter the swap-loop drop by
`source_char_id` — only drop buffs where `source_char_id` is
absent or == self.

v2.49.53 added the source filter to the 🔁 log emission so the
audit entry was correct. v2.49.54 also applies it to the underlying
behavior so the buff itself isn't wrongly dropped.

Tests:
  - Magnus has Paralyzed (source=enemy); casts Hex →
    Paralyzed PRESERVED, Hex installed, no 🔁 log.
  - Magnus has own-anchor concentration; casts Hex → anchor
    DROPPED (v2.49.53 behavior unchanged for the legitimate swap
    case).
"""
import asyncio
from typing import List

from .conftest import CAMPAIGN_ID


async def _seed(gm_client, magnus, pip, magnus_buffs: List[dict]):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_pres_{magnus['id']}",
                    "char_id": magnus["id"],
                    "name": magnus["name"],
                    "initiative": 10,
                    "hp_current": 30,
                    "hp_max": 30,
                    "buffs": magnus_buffs,
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": f"tok_pres_{pip['id']}",
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


async def _buff_keys(gm_client, char_id: int) -> List[str]:
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )
    if r.status_code != 200:
        return []
    return [(b or {}).get("key") for b in r.json().get("buffs", [])]


async def test_paired_buff_preserved_when_caster_swaps(gm_client, roster):
    """Magnus is a Hold Person victim (Paralyzed sourced by enemy=99999).
    Magnus casts Hex. RAW: Magnus's own concentration goes to Hex; the
    Paralyzed buff stays because the enemy is still concentrating on
    Hold Person. Pre-v2.49.54 the swap loop wrongly dropped Paralyzed.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    enemy_id = 99999
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Clear any leftover state.
    for k in ("hex", "paralyzed", "concentration-bless"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    paired = {
        "key": "paralyzed",
        "name": "Paralyzed",
        "icon": "🥶",
        "source_char_id": enemy_id,
        "concentration": True,
        "effects": ["paired condition from enemy caster"],
    }
    await _seed(gm_client, magnus, pip, magnus_buffs=[paired])

    # Pre: Paralyzed is on Magnus.
    pre = await _buff_keys(gm_client, magnus["id"])
    assert "paralyzed" in pre, f"seed failed; got {pre}"

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

    # Post: BOTH Paralyzed AND Hex should be on Magnus.
    post = await _buff_keys(gm_client, magnus["id"])
    assert "paralyzed" in post, (
        f"v2.49.54: paired condition (source=enemy) should NOT be dropped "
        f"when Magnus casts a new concentration spell; got {post}"
    )
    assert "hex" in post, f"Hex install failed; got {post}"

    # Cleanup
    for k in ("hex", "paralyzed"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )


async def test_own_anchor_swap_still_works(gm_client, roster):
    """Regression guard: legitimate own-anchor swap (Magnus carries
    his own concentration anchor; casts Hex) still drops the old
    anchor and installs Hex. The v2.49.54 source filter must not
    over-broaden — own anchors should still be replaced.
    """
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    for k in ("hex", "concentration-bless", "paralyzed"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    own_anchor = {
        "key": "concentration-bless",
        "name": "Concentrating: Bless",
        "icon": "🌀",
        "source_char_id": magnus["id"],
        "concentration": True,
        "effects": ["Concentrating on Bless"],
    }
    await _seed(gm_client, magnus, pip, magnus_buffs=[own_anchor])

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

    post = await _buff_keys(gm_client, magnus["id"])
    assert "concentration-bless" not in post, (
        f"own anchor should still be replaced on legitimate swap; got {post}"
    )
    assert "hex" in post, f"Hex install failed; got {post}"

    # Cleanup
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )
