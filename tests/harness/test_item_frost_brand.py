"""v2.251.0 — magic-items: Frost Brand (RAW DMG p.171, very rare,
attunement). A double-substrate drop-in with ZERO new engine code:

  - the +1d6 cold-on-hit reuses the unconditional attack-rider shape
    (Sun Blade minus the condition predicate) in
    ``_MAGIC_ITEM_ATTACK_RIDERS["frost-brand"]`` — fires on every hit
    while equipped + attuned, surfacing in the /attack response's
    ``auto_uplifts`` with source ``item-frost-brand``;
  - the fire resistance reuses the v2.235.0 ``resistance_to`` passive
    in ``_MAGIC_ITEM_PASSIVES["frost-brand"]`` — folds into the
    aggregated ``resistance_to`` list that ``_resistance_halve``
    consults in the live damage pipeline, surfaced on /sheet-json as
    ``derived.resistances = {types, sources}``.

Demo fixture: Garrik Ironside (Fighter) — the weapon-rider showcase
PC already wielding the fire-themed Flame Tongue — gets the cold-themed
Frost Brand as an additional attuned sword (the seed predates strict
cap enforcement, which lives only on the /attune runtime endpoint).
The Frost Brand attack sits at ``attack_index 4`` (after Greatsword,
Handaxe, Glaive, Flame Tongue). Detuning suppresses BOTH halves.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "frost-brand"
GARRIK_FROST_BRAND_ATTACK_IDX = 4


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 200, "hp_max": 200,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _hp_current(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    sheet = data.get("sheet") or {}
    return int((sheet.get("hp") or {}).get("current") or 0)


async def _deal_damage(gm_client, char_id, naive_current, amount, dtype):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": naive_current},
            "hp_change_reason": "damage",
            "damage_amount": amount,
            "damage_type": dtype,
        },
    )


async def _frost_brand_inv_idx(gm_client, char_id):
    """Resolve the Frost Brand's inventory index from /sheet-json so the
    detune test stays robust against inventory reordering."""
    data = await _sheet_json(gm_client, char_id)
    inv = (data.get("sheet") or {}).get("inventory") or []
    for i, it in enumerate(inv):
        if it.get("_slug") == _SLUG:
            return i
    raise AssertionError(f"Frost Brand not found in inventory: {inv!r}")


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


@pytest_asyncio.fixture
async def garrik_hp_restore(gm_client, roster):
    """Snapshot Garrik's HP and restore it after the test so the
    typed-damage PATCHes don't leak into other tests."""
    g = roster["Garrik Ironside"]
    data = await _sheet_json(gm_client, g["id"])
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    try:
        yield g
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{g['id']}/sheet-fields",
            json={"hp": hp},
        )


async def test_frost_brand_cold_rider_fires(gm_client, garrik):
    """Happy path: attacking any target with the Frost Brand surfaces a
    +1d6 cold uplift (unconditional — no creature-type gate)."""
    g_cid = f"tok_fb_garrik_{garrik['id']}"
    tgt_cid = "tok_fb_target"
    await _seed_battle(gm_client, [
        _mkc(g_cid, garrik["id"], name=garrik["name"]),
        _mkc(tgt_cid, None, name="Bandit", creature_type="humanoid"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": garrik["id"],
            "attack_index": GARRIK_FROST_BRAND_ATTACK_IDX,
            "target_combatant_id": tgt_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Frost Brand Longsword"

    ups = _uplifts(data, "item-frost-brand")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["label"] == "Frost Brand"
    assert rider["expression"] == "1d6"
    assert rider["damage_type"] == "cold"
    # Non-crit 1d6 → [1, 6]; crit-doubled 2d6 → [2, 12].
    assert 1 <= rider["total"] <= 12


async def test_frost_brand_exposes_fire_resistance(gm_client, garrik):
    """The wielder's /sheet-json reports `derived.resistances` listing
    fire, with the Frost Brand named in its sources."""
    data = await _sheet_json(gm_client, garrik["id"])
    res = (data.get("derived") or {}).get("resistances")
    assert res is not None, (
        f"expected derived.resistances, got: {data.get('derived')!r}"
    )
    assert "fire" in (res.get("types") or []), res
    assert any(
        "Frost Brand" in str(s) for s in res.get("sources") or []
    ), f"expected Frost Brand named in sources, got: {res!r}"


async def test_frost_brand_halves_fire_damage(gm_client, garrik_hp_restore):
    """End-to-end: 20 fire damage to the fire-resisted wielder drops HP
    by only 10 — the equipped Frost Brand halves it via
    `_resistance_halve`."""
    g = garrik_hp_restore
    before = await _hp_current(gm_client, g["id"])
    await _deal_damage(gm_client, g["id"], before - 20, 20, "fire")
    after = await _hp_current(gm_client, g["id"])
    assert after == before - 10, (
        f"fire damage not halved by Frost Brand: {before} → {after} "
        f"(expected -10)"
    )


async def test_frost_brand_does_not_halve_cold(gm_client, garrik_hp_restore):
    """Control: 20 COLD damage is unaffected — Frost Brand grants FIRE
    resistance, not cold (it deals cold, it doesn't resist it)."""
    g = garrik_hp_restore
    before = await _hp_current(gm_client, g["id"])
    await _deal_damage(gm_client, g["id"], before - 20, 20, "cold")
    after = await _hp_current(gm_client, g["id"])
    assert after == before - 20, (
        f"cold damage wrongly reduced: {before} → {after} (expected -20)"
    )


async def test_frost_brand_suppressed_when_detuned(gm_client, garrik):
    """Detuning the Frost Brand suppresses BOTH halves: the cold rider
    no longer fires AND fire resistance drops off /sheet-json. Restores
    attunement in teardown."""
    inv_idx = await _frost_brand_inv_idx(gm_client, garrik["id"])
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
        json={"inventory_index": inv_idx, "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        # Fire resistance gone (Garrik has no other passive fire source).
        data = await _sheet_json(gm_client, garrik["id"])
        res = (data.get("derived") or {}).get("resistances") or {}
        assert "fire" not in (res.get("types") or []), (
            f"detuned Frost Brand must drop fire resistance; got {res!r}"
        )

        # Cold rider gone.
        g_cid = f"tok_fb_detune_garrik_{garrik['id']}"
        tgt_cid = "tok_fb_detune_target"
        await _seed_battle(gm_client, [
            _mkc(g_cid, garrik["id"], name=garrik["name"]),
            _mkc(tgt_cid, None, name="Bandit", creature_type="humanoid"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": GARRIK_FROST_BRAND_ATTACK_IDX,
                "target_combatant_id": tgt_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-frost-brand")
        assert ups == [], (
            f"detuned Frost Brand must not fire the cold rider; got {ups!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
            json={"inventory_index": inv_idx, "attuned": True},
        )
