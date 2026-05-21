"""Voluntary /end_buff on a concentration anchor emits a ✋ GM audit log.

v2.49.52 — closes the third concentration-log follow-up filed in
v2.49.50. The three audit causes are now visually distinct in the
GM roll log:

  - 💔 = failed CON save (v2.39.0)
  - 💀 = incapacitated (v2.49.48 0 HP / v2.49.49 death-save / v2.49.51 buff)
  - ✋ = voluntary end (this commit — /end_buff on caster's own anchor)

The ✋ log is only emitted when /end_buff removes a buff that was
(a) flagged concentration=True AND (b) owned by the character (i.e.
source_char_id absent or == self). Ending a paired condition on a
victim (the victim has a concentration-flagged Paralyzed sourced
by an enemy caster) does NOT emit the ✋ log — that's not the
victim voluntarily ending concentration.

Tests:
  - Magnus has Hex; POST /end_buff with key=hex → ✋ log fires.
  - Krieger has Rage (not concentration); /end_buff → NO ✋ log.
  - Victim has Paralyzed (concentration=True but source=enemy);
    /end_buff on Paralyzed → NO ✋ log (victim didn't end their
    own concentration; the source caster is still concentrating).
"""
import asyncio
import time
from typing import List

from .conftest import CAMPAIGN_ID


HOLD_PERSON_INDEX = 8


async def _seed_battle(gm_client, combatants: List[dict]):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _palm_logs(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("roll")
        if (m.get("data") or {}).get("visibility") == "gm_only"
        and "✋" in ((m.get("data") or {}).get("note") or "")
    ]


async def _wait_for_palm_log(gm_ws, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hits = _palm_logs(gm_ws)
        if hits:
            return hits[0]
        await asyncio.sleep(0.02)
    return None


async def test_voluntary_end_concentration_emits_palm_log(gm_client, gm_ws, roster):
    """Magnus casts Hex on Pip; /end_buff on the Hex anchor → ✋ log
    naming Hex fires with breakdown 'voluntary'."""
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Clear any leftover state.
    for k in ("hex", "concentration-hold-person", "paralyzed"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    await _seed_battle(gm_client, [
        {"id": f"tok_vol_{magnus['id']}", "char_id": magnus["id"],
         "name": magnus["name"], "initiative": 10,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_vol_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 9,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
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
    gm_ws.mark()

    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "hex"},
    )
    assert end.status_code == 200, end.text

    log = await _wait_for_palm_log(gm_ws)
    assert log is not None, (
        f"expected ✋ GM log for voluntary Hex end; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )
    note = log["data"]["note"]
    breakdown = log["data"]["breakdown"]
    assert note.startswith("✋"), f"note should start with ✋; got {note!r}"
    assert magnus["name"].split()[0] in note, (
        f"caster name missing; got {note!r}"
    )
    assert "hex" in note.lower(), f"buff name missing; got {note!r}"
    assert "voluntary" in breakdown.lower(), (
        f"breakdown should say 'voluntary'; got {breakdown!r}"
    )


async def test_voluntary_end_non_concentration_buff_no_log(gm_client, gm_ws, roster):
    """Krieger /use_rage installs Rage (not concentration); /end_buff
    on Rage does NOT emit a ✋ log. The log is concentration-specific.
    """
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    await _seed_battle(gm_client, [
        {"id": f"tok_vol_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10,
         "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()

    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert end.status_code == 200, end.text

    # Wait briefly for any spurious broadcasts.
    await asyncio.sleep(0.5)
    palms = _palm_logs(gm_ws)
    assert not palms, (
        f"non-concentration buff /end_buff should NOT emit ✋ log; got "
        f"{[(m.get('data') or {}).get('note') for m in palms]}"
    )


async def test_voluntary_end_paired_condition_no_log(gm_client, gm_ws, roster):
    """Victim has Paralyzed (concentration=True, source=enemy caster).
    Player /end_buff their own Paralyzed → NO ✋ log. The victim
    isn't ending concentration; the source caster is still
    concentrating on Hold Person."""
    tavik = roster["Brother Tavik Stonebrow"]
    magnus = roster["Magnus Hexbinder"]

    saw_install = False
    for _ in range(15):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        for k in ("paralyzed", "hex", "concentration-hold-person"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": tavik["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            {"id": f"tok_vol_{tavik['id']}", "char_id": tavik["id"],
             "name": tavik["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": f"tok_vol_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 9,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": tavik["id"],
                "spell_index": HOLD_PERSON_INDEX,
                "slot_level": 2,
                "class_slug": "cleric",
                "target_character_id": magnus["id"],
                "target_combatant_id": f"tok_vol_{magnus['id']}",
                "target_name": magnus["name"],
                "override": True,
            },
        )
        prompt_id = cast_resp.json()["auto_save_prompt_id"]
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        if r.json().get("auto_buff_installed") == "Paralyzed":
            saw_install = True
            break
    assert saw_install, "no save fail in 15 attempts — flaky env?"

    gm_ws.mark()
    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "paralyzed"},
    )
    assert end.status_code == 200, end.text

    await asyncio.sleep(0.5)
    palms = _palm_logs(gm_ws)
    assert not palms, (
        f"ending a paired condition on a victim should NOT emit ✋ "
        f"(victim isn't the one concentrating); got "
        f"{[(m.get('data') or {}).get('note') for m in palms]}"
    )
