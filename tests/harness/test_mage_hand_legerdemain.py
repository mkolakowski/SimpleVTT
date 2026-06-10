"""v2.99.369 — Arcane Trickster Rogue: Mage Hand Legerdemain (G Rogue sweep, Lv 3+, PHB).

Phase G Rogue archetype sweep — Arcane Trickster was the last
untouched Rogue archetype.
RAW PHB p.97: when you cast Mage Hand, make the spectral hand
invisible and perform extra tasks — stow/retrieve from another's
container, pick locks / disarm traps at range, all controlled as a
bonus action, unnoticed on a Sleight of Hand check.

v1 announce-only — the hand's tasks + Stealth checks are
GM-tracked. No action cost beyond the Mage Hand cast.

Pip Quickfingers (Rogue, PATCHed to Arcane Trickster) is the demo
fixture.

Tests:
  - Lv 7 happy: range 30, invisible True, tasks listed.
  - Wrong subclass (default Thief) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _ml_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mage-hand-legerdemain"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_arcane_trickster(gm_client, roster):
    """PATCH Pip to Arcane Trickster; restore to Thief on teardown."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Arcane Trickster"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief"},
            class_slug="rogue",
        )


def _pc(cid, c, *, hp_max=30):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_pip_in_battle(gm_client, pip):
    """v2.158.17 — `_install_buff` requires an active battle.
    Seed a minimal one with Pip."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_ml_pip_{pip['id']}", pip)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_use_ml_happy(
    gm_client, gm_ws, pip_arcane_trickster,
):
    """Arcane Trickster → invisible hand, range 30, tasks listed,
    buff_installed True."""
    pip = pip_arcane_trickster
    await _seed_pip_in_battle(gm_client, pip)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "mage-hand-legerdemain"
    assert data["range_ft"] == 30
    assert data["invisible"] is True
    assert len(data["tasks"]) >= 1
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _ml_broadcasts(gm_ws, pip["id"])
    assert feats
    assert feats[-1]["data"]["invisible"] is True


async def test_ml_buff_payload_carries_parameter_flags(
    gm_client, gm_ws, pip_arcane_trickster,
):
    """v2.158.17 — state contract (Phase 9): the installed
    `mage-hand-legerdemain-active` buff carries the four
    `mage_hand_legerdemain_*` effect keys with the right values
    (range_ft=30, invisible=True, bonus_action_control=True,
    unnoticed_check="sleight_of_hand_vs_passive_perception").
    Phase 2 (deferred) will have the Mage Hand cast flow read
    these off the caster's `_buffs_active` and surface the
    Legerdemain task picker; this test pins the flag shape so
    that future read site has a stable contract."""
    pip = pip_arcane_trickster
    await _seed_pip_in_battle(gm_client, pip)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    pip_buffs = bu["data"]["buffs"]
    ml_buff = next(
        (b for b in pip_buffs
         if b.get("key") == "mage-hand-legerdemain-active"),
        None,
    )
    assert ml_buff is not None, (
        f"mage-hand-legerdemain-active buff missing; got keys="
        f"{[b.get('key') for b in pip_buffs]}"
    )
    effects = ml_buff.get("effects") or {}
    assert effects.get("mage_hand_legerdemain_range_ft") == 30
    assert effects.get("mage_hand_legerdemain_invisible") is True
    assert effects.get("mage_hand_legerdemain_bonus_action_control") is True
    assert effects.get("mage_hand_legerdemain_unnoticed_check") == (
        "sleight_of_hand_vs_passive_perception"
    )
    # Permanent passive — no concentration, very long duration.
    assert ml_buff.get("concentration") in (False, None)
    assert int(ml_buff.get("duration_rounds") or 0) >= 1000


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


async def test_ml_cast_surfaces_legerdemain_params(
    gm_client, pip_arcane_trickster,
):
    """v2.158.42 — Phase 2 read site for the v2.158.17 Mage Hand
    Legerdemain buff. An Arcane Trickster Pip carrying
    `mage-hand-legerdemain-active` who casts Mage Hand (injected into
    his spell list for the test) sees `/cast_spell` surface the
    Legerdemain parameters: `mage_hand_legerdemain == True`, range 30,
    invisible True, bonus-action control True, unnoticed-check named."""
    pip = pip_arcane_trickster
    await _seed_pip_in_battle(gm_client, pip)
    original = await _sheet_spells(gm_client, pip["id"])
    injected = original + [{
        "name": "Mage Hand", "level": 0, "prepared": True,
        "_slug": "mage-hand", "casting_time": "1 action",
    }]
    await _patch_sheet(gm_client, pip["id"], {"spells": injected})
    try:
        mh_index = await _spell_index_by_slug(
            gm_client, pip["id"], "mage-hand")
        assert mh_index is not None, "Mage Hand not injected"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": pip["id"],
                "spell_index": mh_index,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mage_hand_legerdemain") is True, (
            f"buff + Mage Hand → legerdemain True; got {data}"
        )
        assert data.get("mage_hand_legerdemain_range_ft") == 30
        assert data.get("mage_hand_legerdemain_invisible") is True
        assert data.get("mage_hand_legerdemain_bonus_action_control") is True
        assert data.get("mage_hand_legerdemain_unnoticed_check") == (
            "sleight_of_hand_vs_passive_perception"
        )
    finally:
        await _patch_sheet(gm_client, pip["id"], {"spells": original})


async def test_ml_not_surfaced_on_other_spell(
    gm_client, pip_arcane_trickster,
):
    """Control: with the Legerdemain buff installed, casting a
    non-Mage-Hand spell (Fire Bolt, injected) reports
    `mage_hand_legerdemain == False`. Pins the spell gate (the buff
    alone isn't enough — only a Mage Hand cast surfaces it)."""
    pip = pip_arcane_trickster
    await _seed_pip_in_battle(gm_client, pip)
    original = await _sheet_spells(gm_client, pip["id"])
    injected = original + [{
        "name": "Fire Bolt", "level": 0, "prepared": True,
        "_slug": "fire-bolt", "casting_time": "1 action",
    }]
    await _patch_sheet(gm_client, pip["id"], {"spells": injected})
    try:
        fb_index = await _spell_index_by_slug(
            gm_client, pip["id"], "fire-bolt")
        assert fb_index is not None, "Fire Bolt not injected"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": pip["id"],
                "spell_index": fb_index,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mage_hand_legerdemain") is False, (
            f"non-Mage-Hand spell → legerdemain False; got {data}"
        )
        assert data.get("mage_hand_legerdemain_range_ft") == 0
    finally:
        await _patch_sheet(gm_client, pip["id"], {"spells": original})


async def test_use_ml_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ml_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
