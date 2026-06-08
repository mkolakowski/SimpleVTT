"""Concentration swap — installing a new concentration buff while the
caster already concentrates must KEEP the new anchor.

`_install_buff` enforces RAW one-concentration-at-a-time: a new
concentration buff drops the caster's previous one and fires
`_drop_paired_concentration_buffs` to clean the old spell's paired
conditions. But that cascade removes EVERY concentration buff sourced
by the caster — which, run after the new anchor is installed, also
removed the brand-new anchor, leaving the caster showing as not
concentrating after a swap. This regresses against that.
"""
from .conftest import CAMPAIGN_ID


async def test_concentration_swap_keeps_new_anchor(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]   # Warlock — knows Hex
    krieger = roster["Krieger Stonefist"]
    # Magnus already concentrating on a prior spell; Krieger is the
    # Hex target.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cs_m_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30,
             "buffs": [{
                 "key": "concentration-bless",
                 "name": "Concentrating: Bless",
                 "concentration": True,
                 "source_char_id": magnus["id"],
                 "duration_rounds": 10,
             }],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_cs_k_{krieger['id']}", "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={"character_id": magnus["id"],
              "target_character_id": krieger["id"],
              "slot_level": 1, "ability": "STR", "override": True},
    )
    assert r.status_code == 200, r.text
    got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
    m = next(c for c in combs if c.get("char_id") == magnus["id"])
    keys = {(b or {}).get("key") for b in (m.get("buffs") or [])}
    assert "concentration-bless" not in keys, (
        f"old concentration should be swapped out; got {keys}"
    )
    # Hex's anchor is keyed "hex". It omits source_char_id (so the swap
    # cascade never matched it) — this asserts the swap keeps the new
    # anchor regardless of convention.
    assert "hex" in keys, (
        f"the NEW concentration anchor must survive the swap; got {keys}"
    )
