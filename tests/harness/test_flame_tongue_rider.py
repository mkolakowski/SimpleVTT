"""v2.158.91 — magic-items-automation Phase 5a: Flame Tongue on-hit
rider via `_MAGIC_ITEM_ATTACK_RIDERS` + the existing /attack pipeline.

Different shape from Phases 3 + 4 entirely: no /use_item_action call —
the rider fires from `_compute_attack_auto_uplifts` whenever Garrik
swings his Flame Tongue Longsword (attack._slug == "flame-tongue") and
the matching inventory item is equipped + attuned. RAW DMG p.170:
+2d6 fire on every hit while ablaze; Phase 5a treats "attuned" as
"always ablaze" (Phase 5b will add the bonus-action ignite toggle).

Demo fixture: Garrik Ironside (Champion Fighter Lv 9, +8 attack bonus)
carries a Flame Tongue Longsword at attack_index 3 + inventory_index 7,
equipped + attuned by default.

Tests:
  - happy path: attack with the Flame Tongue → auto_uplifts carries a
    "Flame Tongue" entry with source="item-flame-tongue", fire damage
    type, total in [2, 12] (non-crit 2d6) or [4, 24] (crit-doubled).
  - detune via /attune → no rider on the next attack. Restore in
    teardown.
  - swap to Greatsword (attack_index 0, no _slug match) → no rider
    despite Flame Tongue still being attuned.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


GARRIK_FLAME_TONGUE_ATTACK_IDX = 3   # see _fighter_sheet "attacks"
GARRIK_FLAME_TONGUE_INV_IDX = 7      # see _fighter_sheet "inventory"


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


@pytest_asyncio.fixture
async def garrik(gm_client, roster):
    return roster["Garrik Ironside"]


async def test_flame_tongue_fires_2d6_fire_on_hit(gm_client, gm_ws, garrik):
    """v2.158.91 happy path. Attacking with Flame Tongue at
    attack_index 3 surfaces a +2d6 fire uplift in the response's
    `auto_uplifts` array and the WS broadcast carries the same."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": garrik["id"],
            "attack_index": GARRIK_FLAME_TONGUE_ATTACK_IDX,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Flame Tongue Longsword"

    ups = _uplifts(data, "item-flame-tongue")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["label"] == "Flame Tongue"
    assert rider["damage_type"] == "fire"
    assert rider["expression"] == "2d6"
    # Non-crit 2d6 → [2, 12]; crit-doubled 4d6 → [4, 24].
    assert 2 <= rider["total"] <= 24

    msg = await gm_ws.wait_for("weapon_attack")
    ws_ups = _uplifts(msg["data"], "item-flame-tongue")
    assert len(ws_ups) == 1
    assert ws_ups[0]["damage_type"] == "fire"


async def test_flame_tongue_suppressed_when_detuned(gm_client, garrik):
    """v2.158.91: /attune detune → the next attack has no rider.
    Restores attunement in teardown so subsequent tests see a fresh
    Flame Tongue."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
        json={"inventory_index": GARRIK_FLAME_TONGUE_INV_IDX, "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": GARRIK_FLAME_TONGUE_ATTACK_IDX,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-flame-tongue")
        assert ups == [], (
            "Detuning the Flame Tongue must suppress the rider — "
            f"got {ups!r}"
        )
    finally:
        # Restore attunement so downstream tests see Garrik with the
        # standard demo-seed shape.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/attune",
            json={"inventory_index": GARRIK_FLAME_TONGUE_INV_IDX, "attuned": True},
        )


async def test_non_magic_weapon_has_no_rider(gm_client, garrik):
    """v2.158.91 regression: swinging Garrik's Greatsword
    (attack_index 0, no `_slug` match) doesn't fire the rider even
    though the Flame Tongue is still equipped + attuned in his
    inventory. The double-gate (attack._slug AND matching inventory
    item) blocks the rider from leaking across weapons."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": garrik["id"],
            "attack_index": 0,  # Greatsword
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Greatsword"
    ups = _uplifts(data, "item-flame-tongue")
    assert ups == [], (
        "Greatsword has no `_slug` so the rider must not fire — "
        f"got {ups!r}"
    )
