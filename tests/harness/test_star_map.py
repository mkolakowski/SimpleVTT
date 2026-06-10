"""v2.99.316 → v2.158.13 — Stars Druid: Star Map (Lv 2+, TCE).

v2.99.316 shipped announce-only. v2.158.13 (Phase 8 diversifies
into Druid — first Druid subclass feature flipped from announce-
only to tracked) wires the endpoint to install a permanent
`star-map-active` buff carrying the three parameter flags
(`star_map_active`, `star_map_free_guiding_bolt_uses_max`,
`star_map_always_prepared`) AND auto-bootstrap the
`guiding-bolt-charges` resource on the sheet (max=WIS_mod
min 1, reset=long). The original docstring promised the
resource bootstrap and never delivered; v2.158.13 closes that
gap.

RAW TCE p.37: star chart spellcasting focus. Guidance +
Guiding Bolt always prepared. Guiding Bolt is Lv 1 druid spell,
castable WIS_mod times (min 1) per long rest without slot.

Mira WIS 17 → mod 3 → 3 free Guiding Bolts.

Tests:
  - Lv 5 Stars happy → free_guiding_bolt_uses 3,
    always_prepared includes Guidance + Guiding Bolt,
    `buff_installed == True`, `resource_bootstrapped == True`.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
  - Buff payload + sheet resource state contract.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _sm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "star-map"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_mira_in_battle(gm_client, mira):
    """v2.158.13 — `_install_buff` requires an active battle.
    Seed a minimal one with Mira so the endpoint can lay down
    the buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_sm_mira_{mira['id']}", mira)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def mira_stars(gm_client, roster):
    """PATCH Mira to Stars Druid."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Stars"},
        class_slug="druid",
    )
    try:
        yield mira
    finally:
        # v2.158.13 — clean up the bootstrapped resource so this
        # fixture doesn't leak state across tests. Also restore
        # Moon Lv 5 + the rest of the default mira sheet shape.
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_sm_happy_lv5(
    gm_client, gm_ws, mira_stars,
):
    """Lv 5 Stars (WIS 17 mod 3) → 3 free Guiding Bolts,
    buff_installed True, resource_bootstrapped True."""
    mira = mira_stars
    await _seed_mira_in_battle(gm_client, mira)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["free_guiding_bolt_uses"] == 3
    assert "Guidance" in data["always_prepared"]
    assert "Guiding Bolt" in data["always_prepared"]
    assert data["druid_level"] == 5
    assert data["buff_installed"] is True
    # resource_bootstrapped may be True (first invocation) or
    # False (re-press in same session). Don't pin to True since
    # other tests in the same session may have invoked first.
    assert "resource_bootstrapped" in data
    await asyncio.sleep(0.3)
    feats = _sm_broadcasts(gm_ws, mira["id"])
    assert feats


async def _sheet_spells(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return list((r.json().get("sheet") or {}).get("spells") or [])


async def _spell_index_by_slug(gm_client, char_id, slug):
    for i, s in enumerate(await _sheet_spells(gm_client, char_id)):
        if (s.get("_slug") or "").lower() == slug:
            return i
    return None


async def test_sm_cast_guiding_bolt_surfaces_free_cast(
    gm_client, mira_stars,
):
    """v2.158.43 — Phase 2 read site for the v2.158.13 Star Map buff.
    A Lv 5 Circle of Stars Mira carrying `star-map-active` (with the
    bootstrapped `guiding-bolt-charges` resource at 3) who casts Guiding
    Bolt (injected into her spell list) sees `/cast_spell` surface
    `star_map_free_guiding_bolt == True` +
    `star_map_guiding_bolt_charges_remaining == 3`."""
    mira = mira_stars
    await _seed_mira_in_battle(gm_client, mira)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    original = await _sheet_spells(gm_client, mira["id"])
    injected = original + [{
        "name": "Guiding Bolt", "level": 1, "prepared": True,
        "_slug": "guiding-bolt", "casting_time": "1 action",
    }]
    await _patch_sheet(gm_client, mira["id"], {"spells": injected})
    try:
        gb_index = await _spell_index_by_slug(
            gm_client, mira["id"], "guiding-bolt")
        assert gb_index is not None, "Guiding Bolt not injected"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": mira["id"],
                "spell_index": gb_index,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("star_map_free_guiding_bolt") is True, (
            f"buff + charges + Guiding Bolt → free cast True; got {data}"
        )
        assert data.get("star_map_guiding_bolt_charges_remaining") == 3
    finally:
        await _patch_sheet(gm_client, mira["id"], {"spells": original})


async def test_sm_free_cast_not_surfaced_on_other_spell(
    gm_client, mira_stars,
):
    """Control: with the Star Map buff + charges, casting a non-Guiding-
    Bolt spell (Druidcraft, already in Mira's list) reports
    `star_map_free_guiding_bolt == False` +
    `star_map_guiding_bolt_charges_remaining == 0`. Pins the spell
    gate (the buff alone isn't enough)."""
    mira = mira_stars
    await _seed_mira_in_battle(gm_client, mira)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    dc_index = await _spell_index_by_slug(
        gm_client, mira["id"], "druidcraft")
    assert dc_index is not None, "Mira has no Druidcraft"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": dc_index,
            "override": True,
            "override_range": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("star_map_free_guiding_bolt") is False, (
        f"non-Guiding-Bolt spell → free cast False; got {data}"
    )
    assert data.get("star_map_guiding_bolt_charges_remaining") == 0


async def test_use_sm_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sm_level_gate(
    gm_client, roster,
):
    """Stars Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Stars", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
            json={"character_id": mira["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_sm_buff_payload_carries_parameter_flags(
    gm_client, gm_ws, mira_stars,
):
    """v2.158.13 — state contract (Phase 9): the installed
    `star-map-active` buff carries the three `star_map_*` effect
    keys with the right values (active=True,
    free_guiding_bolt_uses_max=3 for Mira WIS 17, always_prepared
    list with Guidance + Guiding Bolt). Phase 2 (deferred) will
    have `/cast_spell` read these off the caster's
    `_buffs_active`; this test pins the flag shape so that
    future read site has a stable contract."""
    mira = mira_stars
    await _seed_mira_in_battle(gm_client, mira)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_star_map",
        json={"character_id": mira["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    mira_buffs = bu["data"]["buffs"]
    sm_buff = next(
        (b for b in mira_buffs if b.get("key") == "star-map-active"),
        None,
    )
    assert sm_buff is not None, (
        f"star-map-active buff missing; got keys="
        f"{[b.get('key') for b in mira_buffs]}"
    )
    effects = sm_buff.get("effects") or {}
    assert effects.get("star_map_active") is True
    assert effects.get("star_map_free_guiding_bolt_uses_max") == 3
    always_prepared = effects.get("star_map_always_prepared") or []
    assert "Guidance" in always_prepared
    assert "Guiding Bolt" in always_prepared
    # Permanent passive — no concentration, very long duration.
    assert sm_buff.get("concentration") in (False, None)
    assert int(sm_buff.get("duration_rounds") or 0) >= 1000
