"""v2.299.0 — Ring of Spell Turning on the spell-save-advantage roll effect.

The v2.297.0 `spell_save_advantage` roll effect (`_roll_item_spell_save_advantage`)
folds a 2d20kh1 advantage source into the PHB p.173 composition at `/roll` time
when the caller flags the saving throw `vs_spell: true`. This commit lands the
Ring of Spell Turning (RAW DMG p.193, legendary, attunement) on that substrate:
"You have advantage on saving throws against any spell that targets only you."

Carrier: Zara Emberfire (Draconic Sorcerer) carries the ring as inert spare
loot (equipped=False/attuned=False) — she has no other spell-save-advantage
item, so the inert baseline cleanly proves the ring is the source. The tests
PATCH it equipped+attuned, roll a vs_spell save, then restore. The ring's
nat-20 spell-reflection clause is GM-narrated.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_RING = "ring-of-spell-turning"


def _mkc(cid, char_id=None, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 40, "hp_max": 40,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _roll_save(gm_client, char_id, *, stat_key="wis_save",
                     stat_ability="WIS", vs_spell=None):
    body = {
        "expression": "1d20",
        "character_id": char_id,
        "stat_key": stat_key,
        "stat_ability": stat_ability,
    }
    if vs_spell is not None:
        body["vs_spell"] = vs_spell
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll", json=body,
    )


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_item(gm_client, char_id, slug, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, f"carrier has no {slug} item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


@pytest_asyncio.fixture
async def zara(roster):
    return next(v for k, v in roster.items() if "Zara" in k)


async def test_ring_grants_advantage_on_vs_spell_save(gm_client, zara):
    """Equipping+attuning the ring surfaces advantage on a vs_spell save:
    breakdown contains 2d20kh1 + roll_state_applied names the ring."""
    rid = zara["id"]
    snap = await _patch_item(gm_client, rid, _RING, equipped=True, attuned=True)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_ring_{rid}", rid, name="Zara")])
        resp = await _roll_save(gm_client, rid, vs_spell=True)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" in (data.get("breakdown") or ""), (
            f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "auto_advantage_ring_of_spell_turning"
        ), data.get("roll_state_applied")
    finally:
        await _restore(gm_client, rid, snap)


async def test_ring_no_advantage_without_vs_spell_flag(gm_client, zara):
    """The vs_spell gate: the same WIS save WITHOUT the vs_spell flag is a
    straight 1d20 — a plain save must not pick up the spell-only advantage."""
    rid = zara["id"]
    snap = await _patch_item(gm_client, rid, _RING, equipped=True, attuned=True)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_ring_ng_{rid}", rid, name="Zara")])
        resp = await _roll_save(gm_client, rid, vs_spell=False)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _restore(gm_client, rid, snap)


async def test_ring_requires_attunement(gm_client, zara):
    """The ring is an attunement item — equipped-but-unattuned yields no
    advantage even on a vs_spell save (straight 1d20)."""
    rid = zara["id"]
    snap = await _patch_item(gm_client, rid, _RING, equipped=True, attuned=False)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_ring_na_{rid}", rid, name="Zara")])
        resp = await _roll_save(gm_client, rid, vs_spell=True)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _restore(gm_client, rid, snap)


async def test_ring_baseline_has_no_advantage(gm_client, zara):
    """Control: with the ring inert (seed, equipped=False), a vs_spell save
    has no advantage — proving it's ring-sourced."""
    rid = zara["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_ring_base_{rid}", rid, name="Zara")])
    resp = await _roll_save(gm_client, rid, vs_spell=True)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_ring_exposes_derived_flag(gm_client, zara):
    """The wearer's /sheet-json reports derived.spell_save_advantage with the
    ring named in sources when attuned (the v2.236.0 descriptive mirror)."""
    rid = zara["id"]
    snap = await _patch_item(gm_client, rid, _RING, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        flag = (data.get("derived") or {}).get("spell_save_advantage")
        assert flag is not None, (
            f"expected derived.spell_save_advantage, got: {data.get('derived')!r}"
        )
        assert any(
            "Ring of Spell Turning" in str(s)
            for s in (flag.get("sources") or [])
        ), f"expected the ring named in sources, got: {flag!r}"
    finally:
        await _restore(gm_client, rid, snap)
