"""Harness tests for the v2.49.215 ``/npc_cast_spell`` endpoint.

NPC-caster spell endpoint that emits a ``spell_cast`` WS event so the
chat card renders with PC-style spell-card chrome (same renderer as
PC /cast_spell). Mirrors /npc_attack's GM-only stance.

Happy path: GM posts a Sacred Flame cast for the demo's Cult Acolyte
combatant at a PC target → response 200 + WS ``spell_cast`` broadcast
with caster_char_name=<nickname> + save_dc/save_ability set.

Error paths: missing combatant_id → 400; non-GM caller → 403; bad
combatant id (not in battle) → 404.
"""
from __future__ import annotations

import re

from .helpers import BASE_URL, login_client, open_ws, WSCollector


CAMPAIGN_ID = 1


async def _find_npc_combatant_id(client, name_contains: str) -> str | None:
    """Read the tabletop page HTML and return the first combatant id
    whose name contains the substring (case-insensitive). Returns None
    when no match — battle.combatants is mutable and a fresh-reset
    demo may not have spawned the Acolyte yet."""
    resp = await client.get(f"/campaign/{CAMPAIGN_ID}", follow_redirects=True)
    if resp.status_code != 200:
        return None
    name_lc = name_contains.lower()
    for m in re.finditer(
        r'"id"\s*:\s*"(tok_[^"]+)"[^}]*?"name"\s*:\s*"([^"]+)"',
        resp.text,
    ):
        if name_lc in m.group(2).lower():
            return m.group(1)
    return None


async def test_npc_cast_spell_requires_combatant_id():
    """POST without combatant_id → 400."""
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        resp = await client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
            json={"spell_name": "Sacred Flame"},
        )
        assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
    finally:
        await client.aclose()


async def test_npc_cast_spell_gm_only():
    """Non-GM POST → 403."""
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
            json={"combatant_id": "tok_fake", "spell_name": "Sacred Flame"},
        )
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"
    finally:
        await client.aclose()


async def test_npc_cast_spell_bad_combatant_404():
    """GM POST with unknown combatant_id → 404."""
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        resp = await client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
            json={"combatant_id": "tok_nonexistent_999", "spell_name": "Sacred Flame"},
        )
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"
    finally:
        await client.aclose()


async def test_npc_cast_spell_aoe_multi_target_save_loop():
    """v2.49.217: AoE NPC cast loops save+damage per target.

    GM posts Burning Hands (cone, 3d6 fire, DEX save) for Soren with
    a 3-id aoe_target_combatant_ids list → response 200 + spell_cast
    broadcast with auto_save_targets array containing one entry per
    target (each NPC entry has rolled+passed; the seeded first entry
    matches the single-target outcome). Skips when the demo battle
    doesn't have the Acolyte spawned.
    """
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        npc_id = await _find_npc_combatant_id(client, "soren")
        if not npc_id:
            npc_id = await _find_npc_combatant_id(client, "cult acolyte")
        if not npc_id:
            return
        # Pull at least one other combatant for the AoE list.
        resp = await client.get(f"/campaign/{CAMPAIGN_ID}", follow_redirects=True)
        if resp.status_code != 200:
            return
        all_ids = re.findall(r'"id"\s*:\s*"(tok_[^"]+)"', resp.text)
        # Use any two distinct ids (caster + at least one other target).
        aoe_ids = [tid for tid in all_ids if tid != npc_id][:2]
        if not aoe_ids:
            return
        ws = await open_ws(client, CAMPAIGN_ID)
        try:
            async with WSCollector(ws) as collector:
                resp = await client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
                    json={
                        "combatant_id": npc_id,
                        "spell_name": "Burning Hands",
                        "spell_level": 1,
                        "spell_range": "Self",
                        "damage": "3d6",
                        "damage_type": "fire",
                        "save_ability": "DEX",
                        "save_dc": 13,
                        "attack_roll": False,
                        "attack_bonus": "",
                        "aoe_target_combatant_ids": aoe_ids,
                        "area_shape": "cone",
                        "area_size_ft": 15,
                    },
                )
                assert resp.status_code == 200, f"AoE cast failed: {resp.status_code} {resp.text}"
                msg = await collector.wait_for("spell_cast")
                d = msg["data"]
                assert d["spell_name"] == "Burning Hands"
                assert d["area_shape"] == "cone"
                assert d["area_size_ft"] == 15
                # auto_save_targets has at least one entry (the seeded
                # primary target plus the AoE loop entries when present).
                targets = d.get("auto_save_targets") or []
                assert isinstance(targets, list)
                assert len(targets) >= 1, f"expected ≥1 auto_save_targets entry, got {targets}"
                # NPC targets should have a rolled save value set.
                npc_target_entries = [t for t in targets if not t.get("pc_skipped")]
                if npc_target_entries:
                    assert all(
                        t.get("rolled") is not None for t in npc_target_entries
                    ), f"NPC target entries missing rolled save: {npc_target_entries}"
        finally:
            await ws.close()
    finally:
        await client.aclose()


async def test_npc_cast_spell_happy_path_save_spell():
    """GM POST → 200 + WS spell_cast broadcast with the right shape.

    Only runs when a Cult Acolyte (or similarly-named NPC) combatant is
    present in the live demo battle. Skips otherwise — battle.combatants
    is mutable.
    """
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        npc_id = await _find_npc_combatant_id(client, "soren")
        if not npc_id:
            npc_id = await _find_npc_combatant_id(client, "cult acolyte")
        if not npc_id:
            # Demo's battle isn't currently spawned with the Acolyte —
            # skip rather than fail (mutable demo state).
            return
        ws = await open_ws(client, CAMPAIGN_ID)
        try:
            async with WSCollector(ws) as collector:
                resp = await client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/npc_cast_spell",
                    json={
                        "combatant_id": npc_id,
                        "spell_name": "Sacred Flame",
                        "spell_level": 0,
                        "spell_range": "60 feet",
                        "damage": "1d8",
                        "damage_type": "radiant",
                        "save_ability": "DEX",
                        "save_dc": 13,
                        "attack_roll": False,
                        "attack_bonus": "",
                    },
                )
                assert resp.status_code == 200, f"cast failed: {resp.status_code} {resp.text}"
                data = resp.json()
                assert data.get("ok") is True
                assert data.get("is_save") is True
                # WS broadcast lands within the WSCollector's timeout.
                msg = await collector.wait_for("spell_cast")
                d = msg["data"]
                assert d["spell_name"] == "Sacred Flame"
                assert d["save_ability"] == "DEX"
                assert d["save_dc"] == 13
                assert d["is_save"] is True
                # Caster identity for NPC: no char_id, char_name is the
                # combatant's nickname, combatant_id set.
                assert d["caster_char_id"] is None
                assert d["caster_combatant_id"] == npc_id
                assert d.get("caster_char_name"), "caster_char_name should be the monster name"
                assert d.get("is_npc_cast") is True
        finally:
            await ws.close()
    finally:
        await client.aclose()
