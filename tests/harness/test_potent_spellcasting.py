"""v2.99.270 — Light Domain Cleric Lv 8 — Potent Spellcasting (H.1 depth).

H.1 depth ship — first Lv 6/8/17 feature for an already-shipped
Cleric domain. RAW PHB p.60: Light Domain Lv 8+ — add WIS mod
to the damage of any cleric cantrip.

v1 ships announce-only. The /cast_spell damage-roll hook is
filed.

Brother Tavik Stonebrow Lv 8 WIS 16 → +3 mod. Tests PATCH his
subclass to "Light Domain".

Tests:
  - Happy → wis_mod 3, cantrip_name mirrored, broadcast.
  - Wrong subclass (default Life) → 409.
  - Level gate (Lv 7) → 409.
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


def _ps_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "potent-spellcasting"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_light_lv8(gm_client, roster):
    """PATCH Tavik to Light Domain (he's already Lv 8 by default)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain"},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_ps_happy(
    gm_client, gm_ws, tavik_light_lv8,
):
    """Light Tavik Lv 8 → wis_mod 3 + broadcast."""
    tavik = tavik_light_lv8
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
        json={
            "character_id": tavik["id"],
            "cantrip_name": "Sacred Flame",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["wis_mod"] == 3
    assert data["cantrip_name"] == "Sacred Flame"
    await asyncio.sleep(0.3)
    feats = _ps_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ps_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ps_level_gate(
    gm_client, roster,
):
    """Light Tavik at Lv 7 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Light Domain", "level": 7},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 8},
            class_slug="cleric",
        )


async def test_use_ps_knowledge_lv8(
    gm_client, gm_ws, roster,
):
    """v2.99.271 — Knowledge Domain Tavik Lv 8 also works (RAW
    Potent Spellcasting is identical for Light + Knowledge)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Knowledge Domain"},
        class_slug="cleric",
    )
    try:
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["wis_mod"] == 3
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_ps_grave_lv8(
    gm_client, roster,
):
    """v2.99.277 — Grave Domain Tavik Lv 8 also works (XGE p.19)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Grave Domain"},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["wis_mod"] == 3
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_ps_peace_lv8(
    gm_client, roster,
):
    """v2.99.277 — Peace Domain Tavik Lv 8 also works (TCE p.40)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Peace Domain"},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["wis_mod"] == 3
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_ps_buff_payload_carries_wis_mod_and_class_flags(
    gm_client, tavik_light_lv8,
):
    """v2.612.1 — Phase 8 state contract: using Potent Spellcasting now
    installs a permanent `potent-spellcasting-active` buff carrying three
    `potent_spellcasting_*` effect keys (active=True, wis_mod=3 for
    Tavik's WIS 16, class="cleric"). Phase 2 (deferred) will have
    `/cast_spell` read these off the caster's `_buffs_active` and auto-add
    the WIS mod to cleric-cantrip damage; this pins the flag shape so that
    future read site has a stable contract. Pre-clears the permanent buff
    so the assertion is independent of test ordering (the buff persists).
    Seeds a battle with Tavik in it because `_install_buff` requires an
    active battle (returns False otherwise — without the seed this test is
    flaky, passing only when a prior test left a battle active)."""
    tavik = tavik_light_lv8
    # `_install_buff` requires an active battle — seed one with Tavik.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_ps_{tavik['id']}", "char_id": tavik["id"],
                "name": tavik["name"], "initiative": 10,
                "hp_current": 50, "hp_max": 50, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    # The buff is permanent — clear any prior install so we assert a fresh one.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik["id"], "key": "potent-spellcasting-active"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_potent_spellcasting",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("buff_installed") is True
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/buffs"
    )).json().get("buffs", [])
    ps_buff = next(
        (b for b in buffs if b.get("key") == "potent-spellcasting-active"), None,
    )
    assert ps_buff is not None, (
        f"potent-spellcasting-active buff missing; got keys="
        f"{[b.get('key') for b in buffs]}"
    )
    effects = ps_buff.get("effects") or {}
    assert effects.get("potent_spellcasting_active") is True
    assert effects.get("potent_spellcasting_wis_mod") == 3
    assert effects.get("potent_spellcasting_class") == "cleric"
    # Permanent passive — no concentration, very long duration.
    assert ps_buff.get("concentration") in (False, None)
    assert int(ps_buff.get("duration_rounds") or 0) >= 1000
    # Cleanup so the permanent buff doesn't leak to sibling tests.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik["id"], "key": "potent-spellcasting-active"},
    )
