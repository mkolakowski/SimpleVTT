"""v2.297.0 — spell-save-advantage as a live /roll effect.

The v2.236.0 `spell_save_advantage` substrate (Mantle of Spell Resistance,
Spellguard Shield) previously only surfaced a descriptive `/sheet-json`
`derived.spell_save_advantage` flag. This commit upgrades it into a real roll
effect: `_roll_item_spell_save_advantage` folds a 2d20kh1 advantage source into
the PHB p.173 composition at `/roll` time — but ONLY when the caller flags the
saving throw as being against a spell (`vs_spell: true`), since the generic
/roll save can't otherwise know whether a given save is vs a spell (RAW scopes
the advantage to saves vs spells / magical effects).

Carriers:
- Quan Reelstep (Drunken Master Monk) wears the Mantle of Spell Resistance
  equipped+attuned in the seed — so the happy-path + vs_spell-gate tests roll
  on his live loadout with no PATCH.
- Dame Seraphine Vael (Vengeance Paladin) carries a Scarab of Protection (RAW
  DMG p.199) as inert spare loot (the new item this commit lands on the
  substrate) — the tests PATCH it equipped+attuned, roll a vs_spell save, then
  restore.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SCARAB = "scarab-of-protection"


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
async def quan(roster):
    return next(v for k, v in roster.items() if "Quan" in k)


@pytest_asyncio.fixture
async def seraphine(roster):
    return next(v for k, v in roster.items() if "Seraphine" in k)


async def test_mantle_grants_advantage_on_vs_spell_save(gm_client, quan):
    """Quan wears the Mantle (equipped+attuned in seed). A WIS save flagged
    vs_spell rolls 2d20kh1 + roll_state_applied names the mantle."""
    rid = quan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_mantle_{rid}", rid, name="Quan")])
    resp = await _roll_save(gm_client, rid, vs_spell=True)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == (
        "auto_advantage_mantle_of_spell_resistance"
    ), data.get("roll_state_applied")


async def test_mantle_no_advantage_without_vs_spell_flag(gm_client, quan):
    """The vs_spell gate: the same WIS save WITHOUT the vs_spell flag is a
    straight 1d20 — a plain save (e.g. vs a grapple) must not pick up the
    spell-only advantage."""
    rid = quan["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_mantle_ng_{rid}", rid, name="Quan")])
    resp = await _roll_save(gm_client, rid, vs_spell=False)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_scarab_grants_advantage_on_vs_spell_save(gm_client, seraphine):
    """Equipping+attuning the Scarab surfaces advantage on a vs_spell save:
    breakdown contains 2d20kh1 + roll_state_applied names the scarab."""
    rid = seraphine["id"]
    snap = await _patch_item(gm_client, rid, _SCARAB, equipped=True, attuned=True)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_scarab_{rid}", rid, name="Seraphine")])
        resp = await _roll_save(gm_client, rid, vs_spell=True)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" in (data.get("breakdown") or ""), (
            f"Expected 2d20kh1; got breakdown={data.get('breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "auto_advantage_scarab_of_protection"
        ), data.get("roll_state_applied")
    finally:
        await _restore(gm_client, rid, snap)


async def test_scarab_requires_attunement(gm_client, seraphine):
    """The scarab is an attunement item — equipped-but-unattuned yields no
    advantage even on a vs_spell save (straight 1d20)."""
    rid = seraphine["id"]
    snap = await _patch_item(gm_client, rid, _SCARAB, equipped=True, attuned=False)
    try:
        await _seed_battle(gm_client, [_mkc(f"tok_scarab_na_{rid}", rid, name="Seraphine")])
        resp = await _roll_save(gm_client, rid, vs_spell=True)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "2d20kh1" not in (data.get("breakdown") or "")
        assert data.get("roll_state_applied") in (None, "")
    finally:
        await _restore(gm_client, rid, snap)


async def test_scarab_baseline_has_no_advantage(gm_client, seraphine):
    """Control: with the scarab inert (seed, equipped=False), a vs_spell save
    has no advantage — proving it's scarab-sourced."""
    rid = seraphine["id"]
    await _seed_battle(gm_client, [_mkc(f"tok_scarab_base_{rid}", rid, name="Seraphine")])
    resp = await _roll_save(gm_client, rid, vs_spell=True)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_scarab_exposes_derived_flag(gm_client, seraphine):
    """The wearer's /sheet-json reports derived.spell_save_advantage with the
    scarab named in sources when attuned (the v2.236.0 descriptive mirror)."""
    rid = seraphine["id"]
    snap = await _patch_item(gm_client, rid, _SCARAB, equipped=True, attuned=True)
    try:
        data = await _sheet_json(gm_client, rid)
        flag = (data.get("derived") or {}).get("spell_save_advantage")
        assert flag is not None, (
            f"expected derived.spell_save_advantage, got: {data.get('derived')!r}"
        )
        assert any(
            "Scarab of Protection" in str(s)
            for s in (flag.get("sources") or [])
        ), f"expected the scarab named in sources, got: {flag!r}"
    finally:
        await _restore(gm_client, rid, snap)
