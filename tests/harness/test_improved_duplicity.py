"""v2.99.298 → v2.158.3 — Trickery Domain Cleric: Improved Duplicity (Lv 17).

v2.99.298 shipped announce-only. v2.158.3 (Phase 8 third commit
of the [full-feature-automation](../../docs/plans/full-feature-automation.md)
plan; sibling of v2.158.0 Avatar of Battle + v2.158.2 Saint of
Forge and Fire) wires the endpoint to install a permanent
`improved-duplicity` buff carrying the upgraded Invoke Duplicity
parameters: `invoke_duplicity_max_duplicates=4`,
`invoke_duplicity_bonus_move_per_duplicate_ft=30`,
`invoke_duplicity_max_range_ft=120`.

Phase 1 / Phase 2 split (same shape as v2.148.0 Fancy Footwork +
v2.149.0 Relentless Avenger): Invoke Duplicity itself isn't yet
a server-side endpoint, so this is a flag-install whose Phase 2
read site lands when `/use_invoke_duplicity` is shipped.

RAW PHB p.62: Invoke Duplicity now creates up to 4 duplicates
(was 1). Bonus action: move any number of them up to 30 ft
each, max 120 ft from caster.

Tests:
  - Lv 17 happy → max_duplicates 4, bonus_move 30 ft, max
    range 120 ft, buff_installed True.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Installed buff carries the three `invoke_duplicity_*` flags
    on `effects` with the right values.
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


def _id_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-duplicity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """v2.158.3 — `_install_buff` requires an active battle. Seed a
    minimal one with Tavik so the endpoint can lay down the buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_id_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def tavik_trickery_lv17(gm_client, roster):
    """PATCH Tavik to Trickery Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Trickery Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_id_happy_lv17(
    gm_client, gm_ws, tavik_trickery_lv17,
):
    """Lv 17 Trickery → 4 duplicates, 30 ft move, 120 ft range,
    buff_installed True."""
    tavik = tavik_trickery_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_duplicates"] == 4
    assert data["bonus_move_per_duplicate_ft"] == 30
    assert data["max_range_ft"] == 120
    assert data["cleric_level"] == 17
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _id_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_id_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_id_level_gate(
    gm_client, roster,
):
    """Trickery Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Trickery Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_id_buff_payload_carries_invoke_duplicity_flags(
    gm_client, gm_ws, tavik_trickery_lv17,
):
    """v2.158.3 — state contract (Phase 9): the installed
    `improved-duplicity` buff carries the three upgraded Invoke
    Duplicity parameters on `effects`:
      * `invoke_duplicity_max_duplicates: 4`
      * `invoke_duplicity_bonus_move_per_duplicate_ft: 30`
      * `invoke_duplicity_max_range_ft: 120`
    Phase 2 (deferred) will have `/use_invoke_duplicity` read
    these off the caster's `_buffs_active` and substitute the
    upgraded params; this test pins the flag shape so that
    future read site has a stable contract."""
    tavik = tavik_trickery_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    tavik_buffs = bu["data"]["buffs"]
    id_buff = next(
        (b for b in tavik_buffs if b.get("key") == "improved-duplicity"),
        None,
    )
    assert id_buff is not None, (
        f"improved-duplicity buff missing; got keys="
        f"{[b.get('key') for b in tavik_buffs]}"
    )
    effects = id_buff.get("effects") or {}
    assert effects.get("invoke_duplicity_max_duplicates") == 4, (
        f"max_duplicates flag wrong; got effects={effects}"
    )
    assert effects.get("invoke_duplicity_bonus_move_per_duplicate_ft") == 30, (
        f"bonus_move flag wrong; got effects={effects}"
    )
    assert effects.get("invoke_duplicity_max_range_ft") == 120, (
        f"max_range flag wrong; got effects={effects}"
    )
    # Permanent passive — no concentration, very long duration.
    assert id_buff.get("concentration") in (False, None)
    assert int(id_buff.get("duration_rounds") or 0) >= 1000
