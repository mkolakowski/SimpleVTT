"""v2.99.215 — Vanish (Ranger Lv 14+).

Phase F.3 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.92: "Starting at 14th level, you can use the Hide action
as a bonus action on your turn. Also, you can't be tracked by
nonmagical means, unless you choose to leave a trail."

v1 ships announce-style — `/use_vanish` marks the bonus action
slot + broadcasts feature_used. The actual Hide check (Stealth)
is rolled normally via /roll. The "can't be tracked by
nonmagical means" half is filed (SimpleVTT doesn't model
tracking checks).

v2.158.21 — Phase 8 Ranger diversification closes the
twelve-class arc: each press now ALSO installs a permanent
passive ``vanish-active`` buff carrying three ``vanish_*``
parameter flags (active, hide_as_bonus_action,
untrackable_nonmagical). Phase 2 (deferred): action-UI Hide-
as-bonus picker + tracking resolver consume the flags off
``_buffs_active``.

Tests:
  - Happy: Rowan Lv 14 (in battle) → /use_vanish → 200,
    broadcast, buff_installed True.
  - Gate: Rowan Lv 7 → 409 level_too_low.
  - State contract: the installed buff carries the three
    ``vanish_*`` effect keys + permanent duration.
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


def _vanish_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "vanish"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=60):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_rowan_in_battle(gm_client, rowan):
    """v2.158.21 — `_install_buff` requires an active battle."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_vn_rw_{rowan['id']}", rowan)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def rowan_lv14(gm_client, roster):
    """PATCH Rowan to Lv 14. Restore Lv 7 in teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 14},
        class_slug="ranger",
    )
    yield rowan
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 7},
        class_slug="ranger",
    )


async def test_use_vanish_happy_path(
    gm_client, gm_ws, rowan_lv14,
):
    """Rowan Lv 14 → /use_vanish → 200 + broadcast + buff_installed."""
    rowan = rowan_lv14
    await _seed_rowan_in_battle(gm_client, rowan)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "vanish"
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _vanish_broadcasts(gm_ws, rowan["id"])
    assert feats, (
        f"v2.99.215: expected feature_used(source=vanish); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_use_vanish_level_gate(
    gm_client, roster,
):
    """Control: Rowan at Lv 7 → 409 level_too_low."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 14


async def test_use_feature_vanish_curated_entry_resolves_bonus_slot(
    gm_client, rowan_lv14,
):
    """v2.158.23 — server-side `_FEATURE_ECONOMY['vanish']` mirror.

    The cf-use picker routes featureKey === 'vanish' to /use_vanish
    directly (which installs the buff), but the curated server mirror
    exists as a defensive fallback so a /use_feature call with
    ``feature_key: 'vanish'`` resolves the slot to "bonus" instead of
    404-ing on "Unknown feature". This pins the back-compat path.
    """
    rowan = rowan_lv14
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": rowan["id"],
            "feature_key": "vanish",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("slot") == "bonus", (
        f"v2.158.23: /use_feature should resolve `vanish` to the bonus "
        f"slot via the curated table; got slot={data.get('slot')!r}"
    )


async def test_vanish_buff_payload_carries_parameter_flags(
    gm_client, gm_ws, rowan_lv14,
):
    """v2.158.21 — state contract (Phase 9): the installed
    ``vanish-active`` buff carries the three ``vanish_*``
    effect keys with the right values
    (active=True, hide_as_bonus_action=True,
    untrackable_nonmagical=True), is permanent (high duration_rounds)
    and non-concentration."""
    rowan = rowan_lv14
    await _seed_rowan_in_battle(gm_client, rowan)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    rowan_buffs = bu["data"]["buffs"]
    vn_buff = next(
        (b for b in rowan_buffs
         if b.get("key") == "vanish-active"),
        None,
    )
    assert vn_buff is not None, (
        f"vanish-active buff missing; got keys="
        f"{[b.get('key') for b in rowan_buffs]}"
    )
    effects = vn_buff.get("effects") or {}
    assert effects.get("vanish_active") is True
    assert effects.get("vanish_hide_as_bonus_action") is True
    assert effects.get("vanish_untrackable_nonmagical") is True
    # Permanent passive (large duration), not concentration.
    assert vn_buff.get("concentration") in (False, None)
    assert int(vn_buff.get("duration_rounds") or 0) >= 1000
