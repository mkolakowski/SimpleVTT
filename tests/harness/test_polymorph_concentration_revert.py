"""v2.99.172 — Polymorph concentration coupling for the v2.99.168
token-disguise primitive.

Closes a v2.99.168 filed item. When a Polymorph caster's
concentration drops (manual /end_buff on the anchor, new
concentration spell cast, CON save failure on damage), the
target's transform should auto-revert: sheet active_form
clears, the token disguise is removed, broadcasts fire.

Implementation:
  - /transform accepts an optional `caster_char_id` body field.
    When set on a Polymorph cast where caster != target, the
    endpoint installs a `polymorph-active` marker buff on the
    target's combatant entry with source_char_id=caster +
    concentration=True.
  - `_drop_paired_concentration_buffs` (existing v2.38.0 cascade)
    removes the marker when the caster's concentration drops.
  - A new hook in the cascade calls
    `_revert_polymorph_internal(campaign_id, target_char_id)`
    for each removed polymorph-active buff. The helper restores
    the sheet and reverts the token disguise.

Tests:
  - Setup: Thalindra casts Polymorph (installs concentration
    anchor) and then /transform polymorphs Krieger into a Wolf
    with caster_char_id=Thalindra.
  - End Thalindra's anchor via /end_buff.
  - Verify: Krieger's token disguise is reverted + the
    polymorph-active marker is gone from his buffs.
"""
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _get_token_for_char(gm_client, char_id):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in r.json()["tokens"]:
        if t.get("character_id") == char_id:
            return t
    return None


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return r.json().get("buffs") or []


@pytest_asyncio.fixture
async def thalindra_with_l4_slot(gm_client, roster):
    """Thalindra set up to cast Polymorph: an L4 wizard slot + Polymorph
    on her spell list.

    v2.117.0 — restore-safe. Snapshots her original spells + spell_slots
    via the sheet-json endpoint and restores them in teardown (a
    try/finally yield), so a timeout or skip mid-test can't leave her
    spell list corrupted (it used to PATCH spells to [Polymorph] in the
    test body with no restore, which wiped Slow et al. for downstream
    tests like test_concentration_on_damage_cascade).
    """
    thalindra = roster["Thalindra Moonwhisper"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    orig = (snap.json() or {}).get("sheet") or {}
    orig_spells = orig.get("spells") or []
    orig_slots = orig.get("spell_slots") or {}
    test_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": test_slots},
            "spells": [
                {"name": "Polymorph", "level": 4, "_slug": "polymorph",
                 "prepared": True, "casting_time": "1 action"},
            ],
        },
    )
    try:
        yield thalindra
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


async def test_polymorph_concentration_drop_reverts_target(
    gm_client, thalindra_with_l4_slot, roster,
):
    """Thalindra polymorphs Krieger. End Thalindra's concentration
    anchor → Krieger's token disguise is reverted + the
    polymorph-active marker is gone.
    """
    thalindra = thalindra_with_l4_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_pcr_th_{thalindra['id']}"
    kr_tok = f"tok_pcr_kri_{krieger['id']}"
    # Place both tokens.
    await _place_token(gm_client, thalindra["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)
    # Seed battle.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": th_tok, "char_id": thalindra["id"],
             "name": thalindra["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": kr_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 8,
             "hp_current": 75, "hp_max": 75, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Cast Polymorph (installs concentration-polymorph anchor on
    # Thalindra). Polymorph is on her spell list via the
    # thalindra_with_l4_slot fixture (which also restores her original
    # spells in teardown — v2.117.0).
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 4,
            "target_combatant_id": kr_tok,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    # Now /transform Krieger into Wolf with caster_char_id set.
    transform = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/transform",
        json={
            "slug": "wolf", "source": "polymorph",
            "caster_char_id": thalindra["id"],
            "override": True, "free_pick": True,
        },
    )
    if transform.status_code != 200:
        pytest.skip(
            f"/transform returned {transform.status_code}: "
            f"{transform.text[:200]} — Open5e likely unavailable"
        )
    # Sanity: Krieger has the polymorph-active marker + token disguise.
    pre_buffs = await _get_buffs(gm_client, krieger["id"])
    pre_keys = {(b or {}).get("key") for b in pre_buffs}
    assert "polymorph-active" in pre_keys
    pre_token = await _get_token_for_char(gm_client, krieger["id"])
    assert "Wolf" in pre_token["label"]
    # End Thalindra's concentration anchor.
    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={
            "character_id": thalindra["id"],
            "key": "concentration-polymorph",
        },
    )
    assert end.status_code == 200, end.text
    # Verify Krieger's polymorph-active marker is gone.
    post_buffs = await _get_buffs(gm_client, krieger["id"])
    post_keys = {(b or {}).get("key") for b in post_buffs}
    assert "polymorph-active" not in post_keys, (
        f"polymorph-active marker should be removed by the cascade; "
        f"got buffs={post_keys}"
    )
    # Verify Krieger's token disguise is reverted.
    post_token = await _get_token_for_char(gm_client, krieger["id"])
    assert "Wolf" not in post_token["label"], (
        f"Krieger's token label should be restored; got "
        f"{post_token['label']!r}"
    )
    assert post_token.get("disguise") in (None, {}), (
        f"Krieger's token disguise should be cleared; got "
        f"{post_token.get('disguise')!r}"
    )
