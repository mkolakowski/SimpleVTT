"""v2.150.0 — Death Saves Phase 3a: turn-start auto-prompt.

When the turn advances to a PC in `dying` state, the PUT `/battle`
hook broadcasts a `death_save_prompt` event so the owning player's
client can surface a "Roll Death Save" modal automatically. RAW: the
death save is taken at the start of the dying character's turn.

This commit ships the server-side broadcast only — the client UI
modal that consumes the event is a follow-up. The broadcast carries:
- `character_id` / `character_name` — the dying PC
- `combatant_id` — their combatant id in the active battle
- `successes` / `failures` — current death-save counter state
- `source: "turn_start"` — distinguishes from a future
  `force` / `medicine_check` / `gm_override` prompt source

Tests:
  - Happy path: Pip dropped to 0 HP, seed battle with Pip + Tavik on
    Tavik's turn, advance to Pip → `death_save_prompt` fires with
    Pip's `character_id` + the right counter state.
  - Negative path: Pip alive, advance to Pip → no `death_save_prompt`
    broadcast.
"""
import asyncio

from .conftest import CAMPAIGN_ID


def _pc(cid, c):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _drop_to_dying(gm_client, char_id):
    """Drop a PC to 0 HP via the damage path so the Phase 1 state
    machine fires cleanly. Resets dead/stable state first."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 1,
            "damage_type": "slashing",
        },
    )


async def _restore(gm_client, char_id):
    """Reset to alive/full HP on teardown."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def test_death_save_prompt_fires_on_turn_start_for_dying_pc(
    gm_client, gm_ws, roster,
):
    """v2.150.0 — Phase 3a positive: drop Pip to dying, seed battle
    with Pip + Tavik on Tavik's turn (turn_index=1), advance the
    turn to Pip (turn_index=0). Assert the `death_save_prompt`
    broadcast carries Pip's character_id + the right counter state."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    pip_tok = f"tok_dsp_p_{pip['id']}"
    tav_tok = f"tok_dsp_t_{tavik['id']}"
    try:
        await _drop_to_dying(gm_client, pip["id"])
        # Seed on Tavik's turn first so the turn-advance hook fires
        # when we move it to Pip.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [_pc(pip_tok, pip), _pc(tav_tok, tavik)],
                  "turn_index": 1, "round": 1, "active": True},
        )
        gm_ws.mark()
        # Advance to Pip.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [_pc(pip_tok, pip), _pc(tav_tok, tavik)],
                  "turn_index": 0, "round": 1, "active": True},
        )
        msg = await gm_ws.wait_for("death_save_prompt", timeout=2.0)
        d = msg["data"]
        assert int(d.get("character_id") or 0) == int(pip["id"]), (
            f"prompt should be for Pip; got character_id="
            f"{d.get('character_id')!r}"
        )
        assert d.get("combatant_id") == pip_tok
        assert d.get("source") == "turn_start"
        assert int(d.get("successes") or 0) == 0
        assert int(d.get("failures") or 0) == 0
    finally:
        await _restore(gm_client, pip["id"])


async def test_death_save_prompt_does_not_fire_for_alive_pc(
    gm_client, gm_ws, roster,
):
    """v2.150.0 — Phase 3a negative: when the newly-active PC is in
    `alive` state, no `death_save_prompt` broadcast fires. Pin the
    gate so a future regression doesn't spam the broadcast on every
    turn-advance for every healthy PC."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    pip_tok = f"tok_dsp2_p_{pip['id']}"
    tav_tok = f"tok_dsp2_t_{tavik['id']}"
    try:
        await _restore(gm_client, pip["id"])
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [_pc(pip_tok, pip), _pc(tav_tok, tavik)],
                  "turn_index": 1, "round": 1, "active": True},
        )
        gm_ws.mark()
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [_pc(pip_tok, pip), _pc(tav_tok, tavik)],
                  "turn_index": 0, "round": 1, "active": True},
        )
        await asyncio.sleep(0.3)
        prompts = gm_ws.buffered("death_save_prompt")
        assert not prompts, (
            f"no `death_save_prompt` should fire for an alive PC; "
            f"got {prompts}"
        )
    finally:
        await _restore(gm_client, pip["id"])
