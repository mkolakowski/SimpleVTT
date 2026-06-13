"""v2.207.0 — magic-items-automation content tail: Staff of Charming
through the same `/use_item_action` endpoint as the Wand of Fear /
Paralysis, via the generalized `_use_item_action_wand_of_fear`
save-condition handler. RAW DMG p.201 (rare, attunement): 10 charges
(regain 1d8+2 at dawn). The marquee charge-action casts charm person at
one creature within 30 ft — WIS save *at the wielder's spell save DC* or
Charmed for 1 hour.

The handler is content-agnostic. The new wrinkle this commit: the
catalog `action_def` sets `"save_dc": "spell"`, a sentinel that makes the
handler compute the wielder's spell save DC from the sheet
(`_compute_spell_save_dc_from_sheet`) rather than using a fixed number.

Demo home: Lyra Sunstrider (Bard Lv 6, CHA 17, proficiency +3 → spell
save DC 14). She already wears the Cloak of Displacement + Demon Slayer
Rapier, so the staff is her third attuned item (3/3 against the RAW cap).
The staff index is looked up by `_slug`.

Tests:
  - happy: cast at 1 target → save_dc=14 (Lyra's spell save DC),
    save_ability='WIS', charges_spent=1, resource drops 10 → 9.
  - over-cap charges (charges=2 when max=1) → 400.
  - empty staff (current=0) → 409 insufficient_charges.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


def _mkc(cid, char_id=None, name="X", hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1,
        "buffs": [],
        "creature_type": "humanoid",
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


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


@pytest_asyncio.fixture
async def lyra(roster):
    return roster["Lyra Sunstrider"]


@pytest_asyncio.fixture
async def lyra_staff(gm_client, lyra):
    """Force-reseed Lyra's Staff of Charming charge counter to
    current=10 via /sheet-fields PATCH. Snapshot + restore on teardown
    so downstream tests don't see a drained staff. Yields the inventory
    index resolved by `_slug`."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    for i, r in enumerate(resources):
        if isinstance(r, dict) and r.get("key") == "staff-of-charming":
            resources[i] = {**r, "current": 10, "max": 10}
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": resources},
    )
    idx = _slug_index(sheet.get("inventory") or [], "staff-of-charming")
    assert idx >= 0, "Lyra must carry a seeded Staff of Charming"
    yield {"char": lyra, "idx": idx}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": snapshot},
    )


async def test_staff_of_charming_cast_uses_spell_dc(
    gm_client, lyra_staff,
):
    """v2.207.0 happy path. Cast charm person at 1 target → 200 with
    save_dc=14 (Lyra's spell save DC, computed from the sheet via the
    'spell' sentinel), save_ability='WIS', and the charge counter
    drops 10 → 9."""
    lyra = lyra_staff["char"]
    idx = lyra_staff["idx"]
    lyra_cid = f"tok_soc1_lyra_{lyra['id']}"
    a_cid = "tok_soc1_a"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(a_cid, None, name="Bandit Alpha"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-charm-person",
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["item_name"] == "Staff of Charming"
    assert data["save_dc"] == 14  # 8 + prof 3 + CHA mod 3
    assert data["save_ability"] == "WIS"
    assert data["charges_spent"] == 1
    assert data["resource"]["current"] == 9  # 10 → 9
    results = data.get("results") or []
    assert len(results) == 1
    assert results[0].get("combatant_id") == a_cid


async def test_staff_of_charming_over_cap_returns_400(
    gm_client, lyra_staff,
):
    """v2.207.0: charges=2 when catalog max=1 → 400 (shared min/max
    charge validator)."""
    lyra = lyra_staff["char"]
    idx = lyra_staff["idx"]
    lyra_cid = f"tok_soc2_lyra_{lyra['id']}"
    a_cid = "tok_soc2_a"
    await _seed_battle(gm_client, [
        _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
        _mkc(a_cid, None, name="Bandit"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={
            "inventory_index": idx,
            "action_key": "cast-charm-person",
            "charges": 2,
            "target_combatant_ids": [a_cid],
        },
    )
    assert resp.status_code == 400, resp.text


async def test_staff_of_charming_empty_returns_409(
    gm_client, lyra,
):
    """v2.207.0: drain the staff to 0 charges via /sheet-fields, then
    try to cast → 409 insufficient_charges."""
    sheet = await _sheet(gm_client, lyra["id"])
    resources = list(sheet.get("resources") or [])
    snapshot = [dict(r) if isinstance(r, dict) else r for r in resources]
    idx = _slug_index(sheet.get("inventory") or [], "staff-of-charming")
    assert idx >= 0, "Lyra must carry a seeded Staff of Charming"
    drained = [
        {**r, "current": 0}
        if (isinstance(r, dict) and r.get("key") == "staff-of-charming")
        else r
        for r in resources
    ]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
        json={"resources": drained},
    )

    try:
        lyra_cid = f"tok_soc3_lyra_{lyra['id']}"
        await _seed_battle(gm_client, [
            _mkc(lyra_cid, lyra["id"], name=lyra["name"]),
            _mkc("tok_soc3_a", None, name="Bandit"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-charm-person",
                "target_combatant_ids": ["tok_soc3_a"],
            },
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "insufficient_charges"
        assert body.get("current") == 0
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/sheet-fields",
            json={"resources": snapshot},
        )
