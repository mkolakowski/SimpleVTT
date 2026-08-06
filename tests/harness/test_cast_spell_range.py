"""Range enforcement on /cast_spell — Phase 2C of the ruler/range plan.

v2.49.75 — pins the new ``out_of_range`` 409 gate that fires BEFORE
slot consumption when the caster's token + the target's token are
both on the active map AND the parsed spell range can't reach.

Override semantics (mirror the existing Phase 4 over-budget gate):
  - GM:  auto-bypass (rules-authority).
  - Player + override_range=True + strict mode off: bypass.
  - Player + override_range=True + strict mode on: enforced.
  - Player + override_range=False: enforced.

Skip semantics — no 409:
  - Range parses to None (Special / Unlimited / Sight / unknown).
  - Range parses to 0 (Self / Self+radius — no target distance).
  - No active map / caster off-map / target off-map.
  - AoE multi-target cast (target_combatant_ids list non-empty —
    the picker UI handled range).

Tests use Bob's wizard PC (Thalindra) so the non-GM enforcement
paths fire. The GM bypass test uses gm_client.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import ensure_token_at


# Thalindra's spells (v2.49.58 appended Sleep at the end):
FIRE_BOLT_INDEX = 0   # cantrip, 120 ft range
SHIELD_INDEX = 4      # L1, Self range, reaction

# Grid math on the demo map: 70 px = 1 cell = 5 ft.
# Fire Bolt range = 120 ft = 24 cells = 1680 px.
PX_PER_CELL = 70
FT_PER_CELL = 5


@pytest_asyncio.fixture
async def thalindra_with_token(gm_client, roster):
    """Ensure Thalindra has a token on the demo map at (100, 100).
    Returns (character_dict, token_dict). The fixture is GM-driven
    because POST /tokens + token-place are GM-only; the cast itself
    runs as bob_client so the range gate actually fires.

    v2.1047.3: the reposition goes through ``ensure_token_at``, which
    waives the over-speed gate and *asserts* the token landed. It used
    to be fire-and-forget, so a leftover battle 409'd the move and the
    range math below silently measured from the wrong origin.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    # Long-rest to refill slots.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    th_tok = await ensure_token_at(
        gm_client, CAMPAIGN_ID, thalindra["id"], 100, 100)
    return thalindra, th_tok


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()
                 and t["name"].lower() == "bandit"), templates[0])


async def _place_test_npc(gm_client, x: float, y: float, tmpl_id: int,
                          label: str = "Range Test Bandit") -> dict:
    """Create a fresh NPC token at (x, y). Returns the token dict so
    the caller can clean up via DELETE."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl_id,
            "x": x, "y": y,
            "label": label,
            "color": "#cc3333",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _delete_test_npc(gm_client, token_id: int):
    await gm_client.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{token_id}")


async def _seed_battle_with_npc(gm_client, thalindra, bandit_token, bandit_tmpl):
    """Seed a battle with Thalindra + the test NPC. The NPC combatant
    carries ``source_token_id`` pointing at the test token so the
    range helper's _resolve_target_token_pos can resolve position via
    the Token row. Returns the bandit's combatant id."""
    bandit_combatant_id = f"tok_range_{bandit_token['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {
                    "id": f"tok_range_th_{thalindra['id']}",
                    "char_id": thalindra["id"],
                    "name": thalindra["name"],
                    "initiative": 10,
                    "hp_current": 27, "hp_max": 27,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
                {
                    "id": bandit_combatant_id,
                    "char_id": None,
                    "token_template_id": bandit_tmpl["id"],
                    "source_token_id": bandit_token["id"],
                    "name": bandit_token.get("label") or "Range Test Bandit",
                    "initiative": 5,
                    "hp_current": 11, "hp_max": 11,
                    "buffs": [],
                    "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
                },
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return bandit_combatant_id


async def test_in_range_succeeds(gm_client, bob_client, thalindra_with_token):
    """Bob (Thalindra) Fire Bolts a bandit 10 ft away → 200. Range
    check skips because distance (10 ft) ≤ Fire Bolt range (120 ft).
    """
    thalindra, _ = thalindra_with_token
    bandit_tmpl = await _bandit_template(gm_client)
    # 2 cells away = 10 ft. Well under 120 ft.
    bandit = await _place_test_npc(
        gm_client, 100 + 2 * PX_PER_CELL, 100, bandit_tmpl["id"],
        label="Range Test Bandit (in range)",
    )
    try:
        r = await bob_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thalindra["id"],
                "spell_index": FIRE_BOLT_INDEX,
                "target_name": bandit["label"],
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
    finally:
        await _delete_test_npc(gm_client, bandit["id"])


async def test_out_of_range_409(gm_client, bob_client, thalindra_with_token):
    """Bob (Thalindra) Fire Bolts a bandit 350 ft away → 409
    out_of_range with the documented response shape.
    """
    thalindra, _ = thalindra_with_token
    bandit_tmpl = await _bandit_template(gm_client)
    # 70 cells away = 350 ft. Well past Fire Bolt's 120 ft.
    far_x = 100 + 70 * PX_PER_CELL
    bandit = await _place_test_npc(
        gm_client, far_x, 100, bandit_tmpl["id"],
        label="Range Test Bandit (far)",
    )
    try:
        bandit_combatant_id = await _seed_battle_with_npc(
            gm_client, thalindra, bandit, bandit_tmpl,
        )
        r = await bob_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thalindra["id"],
                "spell_index": FIRE_BOLT_INDEX,
                "target_combatant_id": bandit_combatant_id,
                "override": True,  # bypass action-economy gate
            },
        )
        assert r.status_code == 409, r.text
        err = r.json()
        assert err["error"] == "out_of_range"
        assert err["range_ft"] == 120
        # 70 cells × 5 ft/cell = 350.0 (rounded to 0.1)
        assert err["distance_ft"] == 350.0
        assert err["spell_name"] == "Fire Bolt"
        assert err["source_name"] == thalindra["name"]
        assert err["target_name"] == bandit["label"]
    finally:
        await _delete_test_npc(gm_client, bandit["id"])


async def test_override_range_bypasses_409(
    gm_client, bob_client, thalindra_with_token,
):
    """Same out-of-range setup, but body includes override_range=True
    → 200 (player override bypass when strict mode is off).
    """
    thalindra, _ = thalindra_with_token
    bandit_tmpl = await _bandit_template(gm_client)
    far_x = 100 + 70 * PX_PER_CELL
    bandit = await _place_test_npc(
        gm_client, far_x, 100, bandit_tmpl["id"],
        label="Range Test Bandit (override)",
    )
    try:
        bandit_combatant_id = await _seed_battle_with_npc(
            gm_client, thalindra, bandit, bandit_tmpl,
        )
        r = await bob_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thalindra["id"],
                "spell_index": FIRE_BOLT_INDEX,
                "target_combatant_id": bandit_combatant_id,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
    finally:
        await _delete_test_npc(gm_client, bandit["id"])


async def test_gm_bypasses_range_check(gm_client, thalindra_with_token):
    """GM casts at an out-of-range target WITHOUT override_range →
    200 (GM auto-bypass).
    """
    thalindra, _ = thalindra_with_token
    bandit_tmpl = await _bandit_template(gm_client)
    far_x = 100 + 70 * PX_PER_CELL
    bandit = await _place_test_npc(
        gm_client, far_x, 100, bandit_tmpl["id"],
        label="Range Test Bandit (gm bypass)",
    )
    try:
        bandit_combatant_id = await _seed_battle_with_npc(
            gm_client, thalindra, bandit, bandit_tmpl,
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thalindra["id"],
                "spell_index": FIRE_BOLT_INDEX,
                "target_combatant_id": bandit_combatant_id,
                "override": True,
                # No override_range — GM bypasses regardless.
            },
        )
        assert r.status_code == 200, r.text
    finally:
        await _delete_test_npc(gm_client, bandit["id"])


async def test_self_range_skips_check(gm_client, bob_client, thalindra_with_token):
    """Cast a self-range spell (Shield, range="Self") with no target.
    The parser returns 0 → range check skips entirely. 200 (or 409
    no_slot if Thalindra's L1 slots are drained, but the fixture
    long-rested her).
    """
    thalindra, _ = thalindra_with_token
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": SHIELD_INDEX,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text


async def test_off_map_target_skips_check(
    gm_client, bob_client, thalindra_with_token,
):
    """Cast Fire Bolt at a synthesized target (no token on the map).
    The helper's target-resolution returns None for position → check
    skips. 200 even though the named target doesn't exist anywhere
    measurable.
    """
    thalindra, _ = thalindra_with_token
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": FIRE_BOLT_INDEX,
            "target_name": "Imaginary Off-Map Ghost",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
