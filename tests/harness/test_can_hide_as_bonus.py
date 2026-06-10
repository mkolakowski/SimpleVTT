"""v2.158.22 — Phase 2 read site for the v2.158.21 Vanish buff.

GET /api/campaign/{cid}/can_hide_as_bonus?character_id=N returns
whether the PC can Hide as a bonus action right now + the source key
(``"cunning-action"`` / ``"vanish"`` / ``None``).

Tests:
  - Rowan Lv 7 Ranger (no Vanish, no Rogue) → False, source None.
  - Pip Lv 5 Rogue (Cunning Action Lv 2+) → True, source "cunning-action".
  - Rowan Lv 14 Ranger with vanish-active buff installed via
    /use_vanish → True, source "vanish".
  - Rowan Lv 14 Ranger WITHOUT the buff (no /use_vanish call yet) →
    False, source None. Pins the install-then-read contract: the
    helper consults the buff, not just the level.
  - Unknown character_id → 404.
"""
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


def _pc(cid, c, *, hp_max=60):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_rowan_in_battle(gm_client, rowan):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_chab_rw_{rowan['id']}", rowan)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _clear_battle(gm_client):
    """Drop the hub battle state so no stale buffs leak from a
    previous test (the shared Docker container retains in-memory
    battle state between tests — see test-harness-coverage.md note
    on cross-test contention)."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [], "turn_index": 0, "round": 1, "active": False,
        },
    )


@pytest_asyncio.fixture
async def rowan_lv14(gm_client, roster):
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 14}, class_slug="ranger",
    )
    yield rowan
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 7}, class_slug="ranger",
    )


async def test_rowan_lv7_without_vanish_cannot_hide_as_bonus(
    gm_client, roster,
):
    """Ranger Lv 7, no Rogue dip, no buff → False."""
    rowan = roster["Rowan Quickbow"]
    await _clear_battle(gm_client)
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/can_hide_as_bonus",
        params={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["character_id"] == rowan["id"]
    assert data["can_hide_as_bonus"] is False
    assert data["source"] is None


async def test_pip_rogue_lv5_can_hide_via_cunning_action(
    gm_client, roster,
):
    """Rogue Lv 5 → True via Cunning Action (no buff required)."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/can_hide_as_bonus",
        params={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["can_hide_as_bonus"] is True
    assert data["source"] == "cunning-action"


async def test_rowan_lv14_with_vanish_buff_can_hide_via_vanish(
    gm_client, rowan_lv14,
):
    """Ranger Lv 14 + /use_vanish installs the buff → True via "vanish"."""
    rowan = rowan_lv14
    # Wipe any leftover battle/buff state from a sibling test before
    # the "no buff yet" assertion.
    await _clear_battle(gm_client)
    # Without the buff, even at Lv 14 the answer is False — the
    # helper consults the buff, not just the level.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/can_hide_as_bonus",
        params={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["can_hide_as_bonus"] is False
    # Install the buff via /use_vanish.
    await _seed_rowan_in_battle(gm_client, rowan)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True
    # Now the helper reads the buff → True via "vanish".
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/can_hide_as_bonus",
        params={"character_id": rowan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["can_hide_as_bonus"] is True
    assert data["source"] == "vanish"
    # Teardown: clear the battle so the buff doesn't leak to sibling
    # tests that assume a clean slate.
    await _clear_battle(gm_client)


async def test_can_hide_as_bonus_unknown_character_returns_404(
    gm_client,
):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/can_hide_as_bonus",
        params={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
