"""v2.99.326 — Creation College Bard: Mote of Potential (F.1 batch, Lv 3+, TCE).

F.1 Bard subclass batch ship #8 — CLOSES the F.1 Bard batch
(8/8 PHB+XGE+TCE subclasses with first non-spell-only
features wired). RAW TCE p.31: when a creature uses a BI die
from you, the Mote attaches + triggers an effect by mode:
- check: re-roll BI die, add to check.
- attack: BI die in force damage to nearby creature.
- save: temp HP = BI roll + CHA mod.

v1 announce-only — Mote roll + effect application GM-tracked.
No chip — passive rider on existing BI use.

Lyra Lv 6 CHA 17 mod 3 → die 1d8.

Tests:
  - Lv 3+ happy default check → 1d8 + CHA mod 3.
  - mode "attack" passthrough.
  - mode "save" passthrough.
  - Wrong subclass → 409.
  - Creation Lv 2 → 409.
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


def _mp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mote-of-potential"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_creation(gm_client, roster):
    """PATCH Lyra to College of Creation."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Creation"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_mp_happy_lv6_check(
    gm_client, gm_ws, lyra_creation,
):
    """Lv 6 Creation default check → 1d8 + CHA mod 3."""
    lyra = lyra_creation
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "check"
    assert data["die_size"] == 8
    assert data["die_expression"] == "1d8"
    assert data["cha_mod"] == 3
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _mp_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_mp_mode_attack(
    gm_client, lyra_creation,
):
    """mode='attack' passes through."""
    lyra = lyra_creation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "attack"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "attack"


async def test_use_mp_mode_save(
    gm_client, lyra_creation,
):
    """mode='save' passes through."""
    lyra = lyra_creation
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"], "mode": "save"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "save"


async def test_use_mp_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mp_level_gate(
    gm_client, roster,
):
    """Creation Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Creation", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_mote_of_potential",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )
