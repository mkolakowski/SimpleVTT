"""v2.99.279 → v2.134.0 — Ancients Paladin: Aura of Warding.

v2.99.279 shipped announce-only. v2.133.0 ("Spell Tag") added the
`is_spell` plumbing + `resistance_spell_damage` gate. v2.134.0
("Ward Up") wires the endpoint to install the aura-emitting buff so
`_tick_auras` walks the in-range allies on the Paladin's turn-start
and installs the resistance on each. The emitter buff also carries
`effects.resistance_spell_damage: True` directly so the caster
(excluded from `affects: "allies"` per `_tick_auras`) is covered —
the RAW "you and friendly creatures" both halves spell damage.

Caelan Lv 7 → 10 ft radius (30 at Lv 18+). Tests PATCH his
subclass to "Oath of the Ancients" (default is Devotion).

Tests:
  - Lv 7 happy → radius 10, paladin_level 7, aura_installed True.
  - Lv 18 happy → radius 30 (RAW upgrade).
  - Wrong subclass → 409.
  - Level gate (Lv 6) → 409.
  - Caster's emitter buff carries `effects.resistance_spell_damage:
    True` directly + the aura payload's ally-side buff also carries
    the flag (covers RAW "you and friendly creatures").
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


def _aow_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-warding"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_ancients_lv7(gm_client, roster):
    """PATCH Caelan to Ancients. Default Lv 7 already qualifies."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients"},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_aow_happy_lv7(
    gm_client, gm_ws, caelan_ancients_lv7,
):
    """Lv 7 Ancients → radius 10."""
    caelan = caelan_ancients_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 10
    assert data["paladin_level"] == 7
    # v2.134.0 — endpoint now installs the aura buff (was announce-only).
    assert data["aura_installed"] is True
    await asyncio.sleep(0.3)
    feats = _aow_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aow_lv18_radius_upgrade(
    gm_client, caelan_ancients_lv7,
):
    """Lv 18 → radius 30 (RAW upgrade)."""
    caelan = caelan_ancients_lv7
    await _patch_sheet(
        gm_client, caelan["id"], {"level": 18},
        class_slug="paladin",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["radius_ft"] == 30
    assert data["paladin_level"] == 18


async def test_use_aow_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aow_level_gate(
    gm_client, roster,
):
    """Ancients Caelan at Lv 6 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of the Ancients", "level": 6},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
            json={"character_id": caelan["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_aow_buff_grants_caster_self_resistance(
    gm_client, gm_ws, caelan_ancients_lv7,
):
    """v2.134.0 — RAW "you and friendly creatures." The aura's
    `affects: "allies"` filter excludes self per `_tick_auras`, so
    the installed emitter buff ALSO carries
    `effects.resistance_spell_damage: True` directly. Verify the
    `buff_update` broadcast shows the caster's emitter buff with the
    resistance flag + the aura's ally-side buff spec also carries it
    so a Phase 4 tick test can drive Pip's resistance install."""
    caelan = caelan_ancients_lv7
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_aura_of_warding",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    caelan_buffs = bu["data"]["buffs"]
    aura_buff = next(
        (b for b in caelan_buffs if b.get("key") == "aura-of-warding-emitter"),
        None,
    )
    assert aura_buff is not None, (
        f"emitter buff missing from caelan_buffs; got {caelan_buffs}"
    )
    effects = aura_buff.get("effects") or {}
    assert effects.get("resistance_spell_damage") is True, (
        f"caster's emitter buff missing direct "
        f"resistance_spell_damage flag; got effects={effects}"
    )
    aura_spec = effects.get("aura") or {}
    assert aura_spec.get("affects") == "allies"
    assert int(aura_spec.get("radius_ft") or 0) == 10
    ally_buff = aura_spec.get("buff") or {}
    ally_effects = ally_buff.get("effects") or {}
    assert ally_effects.get("resistance_spell_damage") is True, (
        f"aura's ally-side buff payload should carry "
        f"resistance_spell_damage; got {ally_effects}"
    )
