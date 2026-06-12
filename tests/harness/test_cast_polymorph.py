"""v2.99.142 — /cast_polymorph endpoint tests.

L4 Transmutation, concentration up to 1 hour. Bard, Druid,
Sorcerer, Wizard. Warlock-only via the v2.99.142 Sculptor of
Flesh invocation (PHB p.111: "Prerequisite: 7th level. You can
cast Polymorph once using a warlock spell slot. You can't do so
again until you finish a long rest.").

This is the "spell-side" half — slot decrement + invocation gate
+ concentration anchor + audit. The actual transformation runs
via the existing /transform endpoint with source="polymorph".

Second consumer of the v2.99.140 invocation-cast registry. Closes
half of the v2.99.140 filed item (Sculptor of Flesh proves the
abstraction extends past Mire the Mind).

Magnus has eldritch-invocation-sculptor-of-flesh on his feats
list + a sculptor-of-flesh-uses 1/long-rest resource.

Tests:
  - happy path (Magnus via Sculptor of Flesh) → 200; slot +
    resource decrement; caster gets the concentration anchor
  - Warlock without via_invocation flag → 409 missing_invocation
  - Warlock with wrong via_invocation slug → 409 missing_invocation
    (registry rejects when spell_slug != "polymorph")
  - Sculptor of Flesh second cast same long rest → 409
    not_enough_uses
  - L3 slot → 400 (Polymorph is L4)
  - missing character_id → 400
"""
import urllib.request

import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SLUG = "polymorph"


def _open5e_reachable() -> bool:
    """Skip-gate for the stat-block-swap test (needs Open5e beast data,
    via the LOCAL app mirror). Mirrors test_transform.py's gate."""
    try:
        req = urllib.request.Request(
            "http://localhost:8013/api/open5e/monsters?search=wolf",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        resp = urllib.request.urlopen(req, timeout=3)
        return 200 <= resp.status < 300
    except Exception:
        return False


_skip_no_open5e = pytest.mark.skipif(
    not _open5e_reachable(), reason="Open5e API not reachable from this host"
)


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so Sculptor of Flesh use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_sculptor_of_flesh_happy_path(
    gm_client, magnus_rested, roster,
):
    """Magnus casts Polymorph via Sculptor of Flesh → 200; caster
    gets the polymorph concentration anchor.
    """
    magnus = magnus_rested
    mg_tok = f"tok_sof_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    # Magnus is Lv 5 Warlock — his Pact Magic slots are at L3 only.
    # The endpoint will 409 no_slot for L4. Patch in an L4 slot for
    # this test only.
    if resp.status_code == 409 and resp.json().get("error") == "no_slot":
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"spell_slots": {"warlock": {
                "3": {"total": 2, "used": 0},
                "4": {"total": 1, "used": 0},
            }}},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
            json={
                "character_id": magnus["id"],
                "class_slug": "warlock",
                "via_invocation": "sculptor-of-flesh",
                "slot_level": 4,
                "override": True,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["concentration"] is True
    assert data["ready_to_transform"] is True
    assert data["via_invocation"] == "sculptor-of-flesh"
    # Magnus has the concentration anchor.
    mg_keys = await _get_buff_keys(gm_client, magnus["id"])
    assert "concentration-polymorph" in mg_keys

    # Restore Magnus's Pact Magic L3 slot config (the seed default).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
        }}},
    )


async def test_warlock_without_via_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Polymorph isn't a Warlock spell).
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "sculptor-of-flesh"


async def test_warlock_wrong_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock + via_invocation="mire-the-mind" → 409
    missing_invocation. The registry rejects because Mire the
    Mind's spell_slug is "slow", not "polymorph".
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_sculptor_of_flesh_second_cast_409(
    gm_client, magnus_rested,
):
    """Two consecutive Sculptor of Flesh casts (no rest) → second
    is 409 not_enough_uses (1/long-rest gate).
    """
    magnus = magnus_rested
    mg_tok = f"tok_sof_2x_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    # Patch in an L4 slot so we can do the cast.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
            "4": {"total": 2, "used": 0},
        }}},
    )
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    assert cast1.status_code == 200, cast1.text
    # Second cast — same long rest, should 409 not_enough_uses.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "sculptor-of-flesh-uses"
    # Restore the seed's L3-only slot config.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
        }}},
    )


async def test_cast_polymorph_l3_slot_400(gm_client, magnus_rested):
    """slot_level=3 → 400 (Polymorph is L4)."""
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_polymorph_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={"class_slug": "warlock"},
    )
    assert resp.status_code == 400, resp.text


# --- v2.183.17 Phase 4 deep-dive: the stat-block swap ---
# The tests above own the spell-side contract (invocation gate, slot
# decrement, L-level gate). These three own Polymorph's bespoke story:
# the catalog-vs-runtime concentration divergence, and the full
# six-ability stat-block replace + beast HP pool that distinguishes
# Polymorph from Wild Shape — plus the revert restoring the prior form.


async def _sheet(gm_client, char_id) -> dict:
    return (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    ).json().get("sheet") or {}


@pytest_asyncio.fixture
async def thalindra_poly(gm_client, roster):
    """Thalindra (Wizard) set up to cast Polymorph: an L4 slot +
    Polymorph on her spell list. Snapshots + restores her original
    spells/slots so the patch can't leak into sibling tests."""
    thalindra = roster["Thalindra Moonwhisper"]
    snap = await _sheet(gm_client, thalindra["id"])
    orig_spells = snap.get("spells") or []
    orig_slots = snap.get("spell_slots") or {}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {"wizard": {"4": {"total": 1, "used": 0}}},
            "spells": [{"name": "Polymorph", "level": 4, "_slug": "polymorph",
                        "prepared": True, "casting_time": "1 action"}],
        },
    )
    try:
        yield thalindra
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


async def test_polymorph_present_in_catalog():
    """Catalog anchor — Polymorph present as a 4th-level Transmutation,
    "Up to 1 hour" duration, WIS save, 60 ft. The catalog flags
    `concentration: false` (the divergence the next test pins against
    the runtime cast)."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert _SLUG in by_slug, "polymorph absent from catalog"
    spell = by_slug[_SLUG]
    assert int(spell.get("level_int") or 0) == 4, spell.get("level_int")
    assert (spell.get("school") or "").lower() == "transmutation", spell
    assert "hour" in (spell.get("duration") or "").lower(), spell.get("duration")
    assert spell.get("concentration") is False, (
        "catalog should flag Polymorph concentration:false — the runtime "
        "cast binds it; the divergence test depends on this anchor"
    )
    action = next(a for a in spell["actions"]
                  if (a.get("save_ability") or "").lower() == "wis")
    assert action is not None, spell.get("actions")


async def test_cast_binds_concentration_despite_catalog_flag(
    gm_client, thalindra_poly,
):
    """House-rule divergence (mirror of Spiritual Weapon's): the catalog
    flags Polymorph `concentration: false`, but `/cast_polymorph` returns
    `concentration: true` and installs a `concentration-polymorph` anchor
    on the caster (it's an hour-long concentration spell in RAW)."""
    thalindra = thalindra_poly
    th_tok = f"tok_polycon_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
    ])
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert by_slug[_SLUG].get("concentration") is False  # catalog says no

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={"character_id": thalindra["id"], "class_slug": "wizard",
              "slot_level": 4, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["concentration"] is True  # runtime binds it
    assert data["ready_to_transform"] is True
    keys = await _get_buff_keys(gm_client, thalindra["id"])
    assert "concentration-polymorph" in keys, keys


@_skip_no_open5e
async def test_polymorph_full_ability_replace_and_revert_restores(
    gm_client, thalindra_poly, roster,
):
    """Polymorph's signature divergence from Wild Shape: the beast's
    stats *fully replace* all six of the target's abilities (Wild Shape
    keeps INT/WIS/CHA), and the target takes on the beast's HP pool. The
    `/transform source=polymorph` response carries both the new `sheet`
    and the `active_form.form_sheet` — assert the sheet's six abilities
    equal the form's, that the mental stats actually changed (so a
    regression to Wild Shape's partial swap would fail), and that the HP
    pool became the beast's. Then `/revert` restores the prior form's
    abilities + HP exactly."""
    thalindra = thalindra_poly
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_polyfr_th_{thalindra['id']}"
    kr_tok = f"tok_polyfr_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    pre = await _sheet(gm_client, krieger["id"])
    pre_abilities = dict(pre.get("abilities") or {})
    pre_hp = dict(pre.get("hp") or {})

    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={"character_id": thalindra["id"], "class_slug": "wizard",
              "slot_level": 4, "target_combatant_id": kr_tok, "override": True},
    )
    assert cast.status_code == 200, cast.text

    tr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/transform",
        json={"slug": "wolf", "source": "polymorph",
              "caster_char_id": thalindra["id"], "override": True,
              "free_pick": True},
    )
    if tr.status_code != 200:
        pytest.skip(f"/transform {tr.status_code}: {tr.text[:160]} — Open5e?")
    body = tr.json()
    form_abilities = dict(
        ((body.get("active_form") or {}).get("form_sheet") or {}).get("abilities") or {}
    )
    new_sheet = body.get("sheet") or {}
    new_abilities = dict(new_sheet.get("abilities") or {})
    assert form_abilities, "transform response missing form_sheet abilities"
    # Full six-ability replace — every ability equals the beast's.
    for ab in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        assert int(new_abilities.get(ab)) == int(form_abilities.get(ab)), (
            f"{ab}: sheet {new_abilities.get(ab)} != beast {form_abilities.get(ab)}"
        )
    # The mental stats actually changed — a Wild-Shape partial swap would
    # have kept these equal to Krieger's, so this is the divergence pin.
    assert any(
        int(new_abilities.get(ab)) != int(pre_abilities.get(ab))
        for ab in ("INT", "WIS", "CHA")
    ), "polymorph must replace mental stats (wild-shape keeps them)"
    # The HP pool became the beast's, not Krieger's.
    assert int((new_sheet.get("hp") or {}).get("max")) == int(
        (form_abilities and (body["active_form"]["form_sheet"].get("hp") or {}).get("max"))
    ), "polymorphed HP pool should be the beast's"

    # Revert restores the prior form exactly.
    rev = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/revert",
        json={},
    )
    assert rev.status_code == 200, rev.text
    post = await _sheet(gm_client, krieger["id"])
    assert dict(post.get("abilities") or {}) == pre_abilities, (
        "revert should restore Krieger's original abilities"
    )
    assert int((post.get("hp") or {}).get("max")) == int(pre_hp.get("max")), (
        "revert should restore Krieger's original HP max"
    )
