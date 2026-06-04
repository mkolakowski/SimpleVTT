"""v2.99.191 — /battle PUT PC concentration cascade.

Mirror of v2.99.185 for PC casters. v2.99.185 wired the NPC
cascade (`_drop_paired_concentration_buffs_npc`) to fire when an
NPC's concentration buff was removed via `/battle PUT`. PCs have
the same problem: when the GM strikes a PC's concentration buff
from the init tracker's mini-sheet, the underlying PUT writes
the new combatants list without firing the PC mirror cascade
(`_drop_paired_concentration_buffs`), leaving paired conditions
(Hold Person Paralyzed, Hex's caster-side buff, Polymorph
markers, etc.) orphaned on the targets.

v2.99.191 closes the PC path: pre-PUT diff PC combatants for
concentration buff presence; post-PUT diff for absence; for each
PC whose concentration buff was dropped, fire
`_drop_paired_concentration_buffs(campaign_id, char_id)`.

Tests:
  - Setup: Magnus has a concentration buff + Krieger has a
    paired Paralyzed (source_char_id=Magnus,
    _dependent_on_caster_concentration=True). /battle PUT
    removes Magnus's concentration. Verify Krieger's Paralyzed
    is gone via the cascade (read through Krieger's character
    buffs sheet mirror).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs") or []


async def test_battle_put_drops_pc_paired_buffs(
    gm_client, roster,
):
    """Magnus concentrates on Hold Person → Krieger has paired
    Paralyzed (source_char_id=Magnus, dependent on Magnus's
    concentration). /battle PUT with Magnus's concentration buff
    removed → cascade fires → Krieger's Paralyzed is dropped.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    magnus_tok = f"tok_bpct_mg_{magnus['id']}"
    krieger_tok = f"tok_bpct_kr_{krieger['id']}"
    paired_paralyzed = {
        "key": "paralyzed-hold-person",
        "name": "Paralyzed",
        "icon": "⛓️",
        "duration_rounds": 100,
        "duration_max": 100,
        "concentration": False,
        "_dependent_on_caster_concentration": True,
        "source": "hold-person",
        "source_char_id": magnus["id"],
    }
    # Seed Magnus with concentration buff + Krieger with paired
    # Paralyzed sourced from Magnus.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": magnus_tok, "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30,
             "buffs": [{
                 "key": "concentration-hold-person",
                 "name": "Concentrating: Hold Person",
                 "icon": "🕷️",
                 "duration_rounds": 100,
                 "duration_max": 100,
                 "concentration": True,
                 "source": "hold-person",
                 "source_char_id": magnus["id"],
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": krieger_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75,
             "buffs": [paired_paralyzed],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Sanity: Krieger has Paralyzed on his sheet mirror.
    pre_buffs = await _get_buffs(gm_client, krieger["id"])
    pre_keys = {(b or {}).get("key") for b in pre_buffs}
    assert "paralyzed-hold-person" in pre_keys, (
        f"pre-PUT setup: Krieger should have paired Paralyzed; "
        f"got {pre_keys}"
    )
    # /battle PUT with Magnus's concentration buff dropped.
    # Krieger's buffs are passed through unchanged — the cascade
    # is what removes the Paralyzed, not the PUT writeback.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": magnus_tok, "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": krieger_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75,
             "buffs": pre_buffs,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    await asyncio.sleep(0.1)
    post_buffs = await _get_buffs(gm_client, krieger["id"])
    post_keys = {(b or {}).get("key") for b in post_buffs}
    assert "paralyzed-hold-person" not in post_keys, (
        f"v2.99.191: PC cascade should drop Krieger's paired "
        f"Paralyzed when Magnus's concentration is removed via "
        f"/battle PUT; got {post_keys}"
    )
