"""Range enforcement on /place_aoe — Phase 3A of the ruler/range plan.

v2.49.77 — AoE casts (Fireball, Thunderwave, Shatter, etc.) deliberately
skipped server-side range checks in Phase 2 because the legacy
``target_combatant_ids``-list path doesn't carry a cast-point coordinate.
The modern /place_aoe flow DOES carry the picker's chosen ``center: {x,y}``
— so the server can enforce range there. Phase 3A wires that up.

The check compares the picked center to the caster's token position
vs the parsed spell range (stashed at cast time in ``_pending_aoe_casts``).
Same three-tier override as Phase 2C:
  - GM auto-bypass
  - Player + override_range=True + strict mode off → bypass
  - Otherwise enforced

Skip semantics — no 409:
  - Range parses to None / 0 (Self / Unknown).
  - Campaign has no active map.
  - Caster has no token on the active map.

Tests use Bob (Thalindra's owner, non-GM) so the non-GM enforcement
fires. GM-bypass test uses gm_client.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import ensure_token_at

# Demo Thalindra's spells (see test_cast_spell_aoe.py).
FIREBALL_INDEX = 10  # Fireball (range 150 ft) in Thalindra's *stored* sheet.
                     # Was 7, but the demo seed drifted and stored-index 7 is
                     # now Web (range 60 ft), silently breaking the
                     # range_ft==150 assertion below (Web reports 60). Aligned
                     # with test_cast_spell_aoe.py's index map.

# Demo grid: 70 px = 1 cell = 5 ft. Fireball 150 ft = 30 cells = 2100 px.
PX_PER_CELL = 70
# v2.1047.9 — the setup origin must sit ON the 70 px grid. It was 100,
# which is off-grid (100 % 70 == 30), and campaign 1's tokens are
# required to be grid-aligned by
# ``test_demo_campaigns::test_demo_tokens_are_grid_aligned``. That check
# only started failing once v2.1047.5 stopped the demo scheduler from
# wiping the dataset every 60 minutes — the periodic reseed had been
# quietly laundering these leftover positions. Every coordinate below is
# ORIGIN_PX + N * PX_PER_CELL, so moving the origin keeps every distance
# the tests assert on exactly the same.
ORIGIN_PX = 2 * PX_PER_CELL  # 140


@pytest_asyncio.fixture
async def thalindra_at_origin(gm_client, roster):
    """Long-rest Thalindra + place her token at (ORIGIN_PX, ORIGIN_PX). Returns
    the character dict."""
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    # v2.1047.3 — see ensure_token_at: the old fire-and-forget move
    # could 409 against a leftover battle, leaving the AoE origin wrong.
    await ensure_token_at(gm_client, CAMPAIGN_ID, thal["id"], ORIGIN_PX, ORIGIN_PX)
    return thal


async def _init_aoe_cast(client, character_id: int):
    """POST /cast_spell with no targets → pending placement. Returns
    the cast_id."""
    r = await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": character_id,
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("pending_aoe_placement") is True
    return data["id"]


async def test_place_aoe_in_range_succeeds(gm_client, bob_client, thalindra_at_origin):
    """Bob (Thalindra) casts Fireball; places the center 50 ft away.
    Range = 150 ft → 200."""
    thal = thalindra_at_origin
    cast_id = await _init_aoe_cast(bob_client, thal["id"])
    # Center 10 cells away = 50 ft. Within Fireball's 150 ft.
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": [],
            "center": {"x": ORIGIN_PX + 10 * PX_PER_CELL, "y": ORIGIN_PX},
        },
    )
    assert r.status_code == 200, r.text


async def test_place_aoe_out_of_range_409(gm_client, bob_client, thalindra_at_origin):
    """Bob casts Fireball; places the center 350 ft away (well past
    150 ft). Server returns 409 out_of_range with the documented
    response shape."""
    thal = thalindra_at_origin
    cast_id = await _init_aoe_cast(bob_client, thal["id"])
    far_x = ORIGIN_PX + 70 * PX_PER_CELL  # 70 cells × 5 ft = 350 ft
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": [],
            "center": {"x": far_x, "y": ORIGIN_PX},
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "out_of_range"
    assert err["range_ft"] == 150
    assert err["distance_ft"] == 350.0
    assert err["spell_name"] == "Fireball"
    assert err["source_name"] == thal["name"]
    # AoE doesn't have a single "target" — the placement IS the target.
    assert err["target_name"] == "(AoE cast point)"


async def test_place_aoe_override_bypasses_409(
    gm_client, bob_client, thalindra_at_origin,
):
    """Same out-of-range setup + override_range=True → 200 (player
    override bypass when strict mode is off)."""
    thal = thalindra_at_origin
    cast_id = await _init_aoe_cast(bob_client, thal["id"])
    far_x = ORIGIN_PX + 70 * PX_PER_CELL
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": [],
            "center": {"x": far_x, "y": ORIGIN_PX},
            "override_range": True,
        },
    )
    assert r.status_code == 200, r.text


async def test_place_aoe_gm_bypasses_range_check(gm_client, thalindra_at_origin):
    """GM places an out-of-range AoE WITHOUT override_range → 200
    (GM auto-bypass)."""
    thal = thalindra_at_origin
    cast_id = await _init_aoe_cast(gm_client, thal["id"])
    far_x = ORIGIN_PX + 70 * PX_PER_CELL
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": [],
            "center": {"x": far_x, "y": ORIGIN_PX},
            # No override_range — GM bypasses regardless.
        },
    )
    assert r.status_code == 200, r.text
