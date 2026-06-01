"""v2.97.56 — Bardic Inspiration die consumption endpoint.

Closes the API half of the v2.97.30-filed Bardic Inspiration die
consumption UI. A character carrying a ``bardic-inspiration-die`` buff
(granted by an ally Bard's ``/use_bardic_inspiration``) can call
``POST /api/campaign/{cid}/use_bardic_inspiration_die`` to roll the die
and consume it.

Tests:
- Happy path: Lyra inspires Pip; Pip consumes the die via the new
  endpoint with ``context: "attack"``. Asserts response carries the
  die size + a rolled value in [1, die_max] + buff is dropped after.
- Error path: Pip without an active BI buff → 409 ``no_bi_die``.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    combatants = []
    for spec in char_specs:
        combatants.append({
            "id": spec["tok_id"],
            "char_id": spec["id"],
            "name": spec["name"],
            "initiative": spec.get("initiative", 10),
            "hp_current": spec.get("hp_max", 40),
            "hp_max": spec.get("hp_max", 40),
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_consume_bi_die_rolls_drops_buff_and_broadcasts(
    gm_client, gm_ws, roster,
):
    """Lyra inspires Pip; Pip POSTs /use_bardic_inspiration_die with
    context=attack; the server rolls 1d<size>, broadcasts a roll-log
    entry, drops the buff, returns the rolled value.
    """
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])

    # Clean any stale BI buff from a prior test.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bardic-inspiration-die"},
    )

    lyra_tok = f"tok_bidie_lyra_{lyra['id']}"
    pip_tok = f"tok_bidie_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": lyra["id"], "name": lyra["name"], "tok_id": lyra_tok, "hp_max": 35, "initiative": 14},
        {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
    ])

    # Lyra inspires Pip.
    bi_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
        json={
            "character_id": lyra["id"],
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert bi_resp.status_code == 200, bi_resp.text
    die = bi_resp.json().get("die")
    assert die and die.startswith("d"), f"unexpected die size: {die!r}"

    # Verify Pip has the BI buff with the effects marker.
    pip_buffs_pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    bi_buff = next(
        (b for b in pip_buffs_pre if (b or {}).get("key") == "bardic-inspiration-die"),
        None,
    )
    assert bi_buff is not None, f"BI buff not installed; got {pip_buffs_pre}"
    eff = (bi_buff or {}).get("effects") or {}
    assert eff.get("bardic_inspiration_die") == die

    gm_ws.mark()
    # Pip consumes the die on an attack.
    consume = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration_die",
        json={"character_id": pip["id"], "context": "attack"},
    )
    assert consume.status_code == 200, consume.text
    data = consume.json()
    assert data["ok"] is True
    assert data["die"] == die
    assert data["context"] == "attack"
    rolled = int(data["rolled"])
    die_max = int(die[1:])  # "d8" → 8
    assert 1 <= rolled <= die_max, (
        f"rolled={rolled} out of [1, {die_max}] for {die}"
    )

    # Buff should be gone post-consume.
    pip_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "bardic-inspiration-die" for b in pip_buffs_post
    ), f"BI buff still installed post-consume; got {pip_buffs_post}"

    # The roll broadcast carries the expected note prefix.
    import asyncio as _asy
    await _asy.sleep(0.2)
    roll_msgs = gm_ws.buffered("roll")
    consume_msg = next(
        (m for m in roll_msgs
         if "Bardic Inspiration" in (m.get("data") or {}).get("note", "")
         and "attack roll" in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert consume_msg is not None, (
        f"expected a roll broadcast with the BI consume note; "
        f"notes={[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )


async def test_consume_bi_die_without_buff_returns_409(gm_client, roster):
    """No BI buff installed → 409 ``no_bi_die``."""
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, pip["id"])
    # Ensure no BI buff.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bardic-inspiration-die"},
    )

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration_die",
        json={"character_id": pip["id"], "context": "save"},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "no_bi_die"


# v2.99.31 — stat_key + stat_ability for richer chat-card text.
# When the player consumes the die on a SPECIFIC roll (Athletics
# check, Persuasion check, STR save, etc.), the chat-card note can
# carry the specific skill / ability instead of the generic
# "ability check" label.


async def test_consume_bi_die_with_skill_stat_key_uses_skill_label(
    gm_client, gm_ws, roster,
):
    """Lyra inspires Pip; Pip consumes the die with
    stat_key="Athletics" + stat_ability="STR". Roll note carries
    "Athletics check" instead of the generic "ability check".
    """
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bardic-inspiration-die"},
    )
    lyra_tok = f"tok_bidie2_lyra_{lyra['id']}"
    pip_tok = f"tok_bidie2_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": lyra["id"], "name": lyra["name"], "tok_id": lyra_tok, "hp_max": 35, "initiative": 14},
        {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
    ])
    bi_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
        json={
            "character_id": lyra["id"],
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert bi_resp.status_code == 200

    gm_ws.mark()
    consume = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration_die",
        json={
            "character_id": pip["id"],
            "context": "check",
            "stat_key": "Athletics",
            "stat_ability": "STR",
        },
    )
    assert consume.status_code == 200, consume.text
    data = consume.json()
    assert data["stat_key"] == "Athletics"
    assert data["stat_ability"] == "STR"
    assert data["context_label"] == "Athletics check"

    import asyncio as _asy
    await _asy.sleep(0.2)
    roll_msgs = gm_ws.buffered("roll")
    consume_msg = next(
        (m for m in roll_msgs
         if "Bardic Inspiration" in (m.get("data") or {}).get("note", "")
         and "Athletics check" in (m.get("data") or {}).get("note", "")),
        None,
    )
    assert consume_msg is not None, (
        f"expected note containing 'Athletics check'; got notes="
        f"{[(m.get('data') or {}).get('note') for m in roll_msgs]}"
    )


async def test_consume_bi_die_with_ability_check_stat_key_uses_ability_label(
    gm_client, gm_ws, roster,
):
    """Raw ability check shape: stat_key="str_check" + stat_ability="STR"
    → context_label is "STR check".
    """
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "bardic-inspiration-die"},
    )
    lyra_tok = f"tok_bidie3_lyra_{lyra['id']}"
    pip_tok = f"tok_bidie3_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": lyra["id"], "name": lyra["name"], "tok_id": lyra_tok, "hp_max": 35, "initiative": 14},
        {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
    ])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
        json={
            "character_id": lyra["id"],
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
        },
    )
    consume = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration_die",
        json={
            "character_id": pip["id"],
            "context": "check",
            "stat_key": "str_check",
            "stat_ability": "STR",
        },
    )
    assert consume.status_code == 200, consume.text
    data = consume.json()
    assert data["context_label"] == "STR check"
