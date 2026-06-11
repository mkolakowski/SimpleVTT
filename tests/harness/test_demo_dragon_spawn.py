"""v2.158.99 — magic-items-automation Phase 6c: the Young Red Dragon
(template wired in v2.158.98) is now spawned on the Tavern Brawl map
by default + added to the pre-rolled init. CR 10 vs. Lv 5-9 PCs is
deliberately unbalanced — it's a showcase for Caelan's Dragon Slayer
rider firing automatically via the v2.158.96+5f+98 template-resolution
path, not a winnable encounter.

Tests verify the demo's persisted battle state (queried via
``GET /battle``, which mirrors the seeded `reset_and_reseed` push to
the realtime hub) contains a Drakkasha combatant with a
``token_template_id`` that points to the v2.158.98 dragon template.

NOTE: tests in the broader suite (e.g. test_demon_slayer_rider.py)
mutate the live battle state via ``PUT /battle``, so a serial harness
run will see a polluted state by the time this file fires. The fix
is to restart the container before this test fires; in CI the runner
is fresh per push, and locally a ``docker compose restart app``
between sessions is the standing recipe. The HTTP harness coverage
doc's "Run against a FRESH DB" warning covers this.
"""
from .conftest import CAMPAIGN_ID


async def test_yrd_combatant_in_seeded_battle_state(gm_client):
    """v2.158.99: the demo seed's reset_and_reseed pushes the
    14-combatant Tavern Brawl battle state into the hub + persists
    it to the Battle table. GET /battle reads that state. The
    combatants list should include "Drakkasha (Young Red Dragon)" at
    hp_max=178 with token_template_id set so the v2.158.96 Phase 5f
    resolver can fire Caelan's Dragon Slayer rider on attack."""
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert resp.status_code == 200, resp.text
    state = (resp.json() or {}).get("battle") or {}
    combatants = state.get("combatants") or []
    drakkasha = next(
        (c for c in combatants if "Drakkasha" in (c.get("name") or "")),
        None,
    )
    assert drakkasha is not None, (
        f"Drakkasha not in /battle combatants — broader harness suite "
        f"may have overwritten the seeded state via PUT /battle. "
        f"Recipe: docker compose restart app, then re-run.\n"
        f"Names found: {[c.get('name') for c in combatants]}"
    )
    assert drakkasha.get("hp_max") == 178, (
        f"Drakkasha HP should be 178 RAW; got {drakkasha.get('hp_max')}"
    )
    assert drakkasha.get("token_template_id") is not None, (
        "Drakkasha combatant must carry token_template_id so the "
        "Phase 5f helper can resolve sheet.type='dragon'."
    )


async def test_yrd_template_has_creature_type_dragon(gm_client):
    """v2.158.99: belt-and-braces — the Drakkasha combatant's
    token_template_id should resolve to a TokenTemplate whose
    sheet.type == "dragon". Looks up the template via /templates
    rather than dereferencing the combatant's template_id directly
    (more robust against future schema shifts)."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    yrd = next(
        (t for t in templates if t.get("name") == "Young Red Dragon"),
        None,
    )
    assert yrd is not None, (
        f"Young Red Dragon template missing; got: "
        f"{[t.get('name') for t in templates]}"
    )
    assert (yrd.get("sheet") or {}).get("type") == "dragon", (
        f"YRD template's sheet.type must be 'dragon'; got "
        f"{(yrd.get('sheet') or {}).get('type')!r}"
    )
