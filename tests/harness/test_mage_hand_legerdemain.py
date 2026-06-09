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
