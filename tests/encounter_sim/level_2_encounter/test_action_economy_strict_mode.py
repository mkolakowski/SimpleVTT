"""test_action_economy_strict_mode — Phase 3 (Level 2), commit J.

Validates the **strict-action-economy** gate. Under normal
(non-strict) conditions, a player who's already used their action
slot can re-fire ``/attack`` with ``override=true`` and the server
proceeds (the client-side modal asks the player to confirm; the
server trusts the override flag). Under strict conditions, the
override flag is ignored for non-GM users and the 409 response
carries ``strict: true`` so the client modal hides its Confirm
button.

GM-as-driver doesn't exercise this gate at all — the
``_user_is_gm`` short-circuit in the endpoint bypasses both the
override flag AND the strict flag. The test therefore must drive
from Alice (a non-GM demo player who owns Pip Quickfingers).

Scenario:
  1. Enable ``strict_action_economy`` campaign setting + restore
     ``auto_apply_damage`` (the settings endpoint clears omitted
     checkboxes, so we preserve it explicitly).
  2. PUT a battle state where Pip's action slot is already used
     (``economy.action = True``).
  3. Alice POSTs ``/attack`` for Pip's Shortsword with
     ``override=True``.
  4. Assert 409 + ``strict: true`` in the response body.
  5. Teardown: disable strict_action_economy so subsequent tests
     run under the demo default. Critical — strict mode persists in
     the campaign row.
"""
from __future__ import annotations

from playwright.sync_api import BrowserContext

from ..helpers.battle import (
    CAMPAIGN_ID,
    make_combatant,
    post_attack_as_player,
    seed_battle,
    set_strict_action_economy,
)


PIP_CID = "es_strict_pip"
BANDIT_CID = "es_strict_bandit"


def test_strict_mode_gates_non_gm_player_with_override(
    gm_context: BrowserContext,
    roster: dict,
):
    pip = roster["Pip Quickfingers"]

    # Seed battle WITH Pip's action slot already used so the gate
    # actually fires (the gate is ``was_used + not_gm + not_override``).
    pip_combatant = make_combatant(
        PIP_CID, char_id=pip["id"], name="Pip Quickfingers",
        hp_cur=35, hp_max=35, initiative=15,
    )
    pip_combatant["economy"]["action"] = True
    combatants = [
        pip_combatant,
        make_combatant(
            BANDIT_CID, name="Bandit Alpha", hp_cur=30, hp_max=30, initiative=10,
        ),
    ]
    seed_battle(combatants)
    set_strict_action_economy(True)

    try:
        # Alice (non-GM) POSTs /attack with override=true. Without
        # strict mode this would succeed; with strict it must 409.
        resp = post_attack_as_player(
            "demo-alice@example.com", "demopass",
            character_id=pip["id"],
            attack_index=0,
            target_combatant_id=BANDIT_CID,
            override=True,
        )

        # ── Layer 1: HTTP 409 + strict flag ───────────────────────
        assert resp.status_code == 409, (
            f"expected 409 (strict gate); got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body.get("error") == "over_budget", (
            f"expected error=over_budget; got {body}"
        )
        assert body.get("strict") is True, (
            f"expected strict:true so client modal hides Confirm; got {body}"
        )
        # The server should echo the slot so the client modal can
        # tell the player which budget they hit.
        assert body.get("slot") == "action", f"expected slot=action; got {body}"
    finally:
        # ── Teardown: restore demo default ────────────────────────
        # Strict mode is a campaign-level toggle that PERSISTS in the
        # DB. Without this teardown, every subsequent test that
        # depends on Alice/Bob playing freely would fail.
        set_strict_action_economy(False)
