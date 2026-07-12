"""v2.99.348 — Moon Druid: Combat Wild Shape (E.4 Druid batch CLOSE, Lv 2+, PHB).

Phase E.4 Druid subclass batch — Moon was the last untouched
circle; this ship CLOSES the batch (7/7).
RAW PHB p.69: use Wild Shape as a bonus action (not an action);
while transformed, spend a bonus action + one spell slot to
regain 1d8 HP per slot level.

v2.1002.0 (Phase 8) — heal mode now APPLIES the rolled HP to the
druid via `_apply_heal_to_combatant` (the Undying Sentinel self-apply
shape), surfacing `heal_applied` / `hp_after` / `revived`. Still
GM-tracked: the transform itself, the spell-slot spend, and the
"while transformed" prerequisite. Bonus chip. Two modes:
  - no slot_level → announce bonus-action Wild Shape.
  - slot_level >= 1 → roll <slot_level>d8 and apply the heal.

Mira Greenleaf (Circle of the Moon Lv 5) is the demo fixture.

Tests:
  - Transform mode happy (no slot_level) → mode "transform".
  - Heal mode happy (slot_level=2) → mode "heal", heal in [2,16].
  - Heal mode state assertion (Phase 9 contract) → sheet HP actually
    rises by heal_applied from a damaged baseline.
  - Wrong subclass (Circle of the Land) → 409.
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


def _cws_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "combat-wild-shape"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_moon(gm_client, roster):
    """Ensure Mira is Circle of the Moon Lv 5 (her default)."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Moon", "level": 5},
        class_slug="druid",
    )
    yield mira
    # Mira's baseline already is Circle of the Moon; no teardown
    # needed beyond what other Druid fixtures restore.


async def test_use_cws_transform_happy(
    gm_client, gm_ws, mira_moon,
):
    """Lv 5 Moon Druid, no slot_level → mode 'transform'."""
    mira = mira_moon
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_wild_shape",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "combat-wild-shape"
    assert data["mode"] == "transform"
    assert data["heal_amount"] == 0
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _cws_broadcasts(gm_ws, mira["id"])
    assert feats
    assert feats[-1]["data"]["mode"] == "transform"


async def test_use_cws_heal_happy(
    gm_client, gm_ws, mira_moon,
):
    """Lv 5 Moon Druid, slot_level 2 → mode 'heal', 2d8 in [2,16]."""
    mira = mira_moon
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_wild_shape",
        json={"character_id": mira["id"], "slot_level": 2, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "heal"
    assert data["slot_level"] == 2
    assert 2 <= data["heal_amount"] <= 16
    await asyncio.sleep(0.3)
    feats = _cws_broadcasts(gm_ws, mira["id"])
    assert feats
    assert feats[-1]["data"]["heal_amount"] == data["heal_amount"]


async def test_use_cws_heal_applies_hp(
    gm_client, mira_moon,
):
    """v2.1002.0 Phase 9 state contract — the heal actually lands on
    the sheet: damage Mira to (max - 20), heal with a Lv 2 slot, and
    the sheet's hp.current rises by exactly heal_applied."""
    mira = mira_moon
    data0 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-json",
    )).json()
    hp_max = int(((data0.get("sheet") or {}).get("hp") or {}).get("max") or 0)
    assert hp_max >= 21, f"fixture needs headroom; hp_max={hp_max}"
    damaged = hp_max - 20
    await _patch_sheet(
        gm_client, mira["id"], {"hp": {"current": damaged}},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_combat_wild_shape",
            json={"character_id": mira["id"], "slot_level": 2,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["mode"] == "heal"
        # 20 HP of headroom vs a 2d8 roll (max 16) → full heal lands.
        assert data["heal_applied"] == data["heal_amount"], data
        assert data["revived"] is False
        after = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-json",
        )).json()
        hp_after = int(
            ((after.get("sheet") or {}).get("hp") or {}).get("current") or 0
        )
        assert hp_after == damaged + data["heal_applied"], (
            f"sheet hp {hp_after} != {damaged} + {data['heal_applied']}"
        )
        assert data["hp_after"] == hp_after, data
    finally:
        await _patch_sheet(
            gm_client, mira["id"], {"hp": {"current": hp_max}},
        )


async def test_use_cws_wrong_subclass(
    gm_client, roster,
):
    """Mira PATCHed to Circle of the Land → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Land"},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_combat_wild_shape",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_cws_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_wild_shape",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
