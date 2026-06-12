"""v2.165.0 — /api/campaign/{cid}/spend_legendary_resistance — Phase 2a
of `docs/plans/legendary-actions.md`. The per-day legendary-resistance
pool: a legendary creature spends one resistance to turn a failed save
into a success (RAW MM p.11).

The pool's ``max`` seeds from the creature's stat block — the Adult Red
Dragon carries "Legendary Resistance (3/Day)", projected to
``legendary_resistance_per_day = 3`` by ``_monster_dict_to_sheet``.

Coverage:
  - happy path: first spend drops the pool 3 → 2 + broadcasts
    `legendary_resistance_spent(reason=spent)`.
  - draining: 3 spends → pool 0; 4th attempt → 409
    `insufficient_legendary_resistance`.
  - 409 `no_legendary_resistance` for a non-legendary combatant (a
    bandit, no Legendary Resistance special ability).
  - 404 unknown combatant.
  - 400 missing combatant_id.
  - 403 non-GM caller.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", initiative=10,
         token_template_id=None):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": initiative,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _template_id_by_name(gm_client, name):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert resp.status_code == 200, resp.text
    for t in resp.json():
        if t.get("name") == name:
            return t["id"]
    raise AssertionError(
        f"No {name!r} template in the demo seed. "
        f"Found: {[t.get('name') for t in resp.json()]}"
    )


@pytest_asyncio.fixture
async def adult_red_dragon_template_id(gm_client):
    return await _template_id_by_name(gm_client, "Adult Red Dragon")


@pytest_asyncio.fixture
async def bandit_template_id(gm_client):
    return await _template_id_by_name(gm_client, "Bandit")


async def _seed_battle(gm_client, combatants, turn_index=0):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": turn_index,
            "round": 1,
            "active": True,
        },
    )


async def test_spend_legendary_resistance_decrements_pool(
    gm_client, gm_ws, adult_red_dragon_template_id,
):
    """First spend drops the Adult Red Dragon's pool 3 → 2 + broadcasts."""
    dragon_cid = "npc_lr_spender"
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=256, hp_max=256, name="Adult Red Dragon",
             initiative=20, token_template_id=adult_red_dragon_template_id),
        _mkc("filler_lr", hp_cur=10, hp_max=10, name="Filler", initiative=5),
    ], turn_index=0)

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"combatant_id": dragon_cid},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["combatant_id"] == dragon_cid
    assert data["max"] == 3
    assert data["current"] == 2  # 3 → 2

    msg = await gm_ws.wait_for("legendary_resistance_spent")
    assert msg["data"]["combatant_id"] == dragon_cid
    assert msg["data"]["max"] == 3
    assert msg["data"]["current"] == 2
    assert msg["data"]["reason"] == "spent"
    assert msg["data"]["combatant_name"] == "Adult Red Dragon"


async def test_spend_legendary_resistance_drains_to_zero_then_409(
    gm_client, adult_red_dragon_template_id,
):
    """Three spends drain the 3/day pool; the fourth 409s."""
    dragon_cid = "npc_lr_drain"
    await _seed_battle(gm_client, [
        _mkc(dragon_cid, hp_cur=256, hp_max=256, name="Adult Red Dragon",
             initiative=20, token_template_id=adult_red_dragon_template_id),
        _mkc("filler_lr2", hp_cur=10, hp_max=10, name="Filler", initiative=5),
    ], turn_index=0)

    expected = [2, 1, 0]
    for want in expected:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
            json={"combatant_id": dragon_cid},
        )
        assert r.status_code == 200, r.text
        assert r.json()["current"] == want

    # Pool now 0; next spend 409s.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"combatant_id": dragon_cid},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "insufficient_legendary_resistance"
    assert body["current"] == 0
    assert body["max"] == 3


async def test_spend_legendary_resistance_non_legendary_409(
    gm_client, bandit_template_id,
):
    """A bandit has no Legendary Resistance special ability → 409
    no_legendary_resistance (max 0)."""
    bandit_cid = "npc_lr_bandit"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=40, hp_max=40, name="Bandit", initiative=12,
             token_template_id=bandit_template_id),
        _mkc("filler_lr3", hp_cur=10, hp_max=10, name="Filler", initiative=5),
    ], turn_index=0)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"combatant_id": bandit_cid},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "no_legendary_resistance"


async def test_spend_legendary_resistance_unknown_combatant_404(
    gm_client, adult_red_dragon_template_id,
):
    """An id not in the active battle → 404."""
    await _seed_battle(gm_client, [
        _mkc("npc_lr_present", hp_cur=256, hp_max=256, name="Adult Red Dragon",
             initiative=20, token_template_id=adult_red_dragon_template_id),
    ], turn_index=0)

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"combatant_id": "npc_does_not_exist"},
    )
    assert resp.status_code == 404


async def test_spend_legendary_resistance_missing_combatant_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={},
    )
    assert resp.status_code == 400


async def test_spend_legendary_resistance_player_caller_403(alice_client):
    """Non-GM players cannot spend an NPC's legendary resistance."""
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"combatant_id": "npc_lr_spender"},
    )
    assert resp.status_code == 403
