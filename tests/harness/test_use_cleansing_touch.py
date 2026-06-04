"""v2.99.157 — /use_cleansing_touch endpoint tests.

Cleansing Touch is a Paladin Lv 14+ feature (PHB p.85): action
to end one spell on yourself or a willing creature you touch.
CHA mod uses per long rest (min 1). First mechanically-wired
Paladin Lv 14+ feature.

Sir Caelan's seed gains the `cleansing-touch-uses` resource at
3/3 (his CHA mod is +3). Shown descriptively at Lv 6; the
endpoint enforces the Lv 14+ gate.

v1 simplifications: no range/touch check (GM-adjudicated), no
"willing creature" gate, ends ONE named buff per use.

Tests:
  - happy path (Caelan @ Lv 14, target has a buff to end) →
    200; buff removed from target; resource decrements
  - level gate (Caelan @ stock Lv 6) → 409 missing_feature
  - target has no matching buff → 409 buff_not_found
  - target combatant not in battle → 404 target_not_found
  - missing fields → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": list(buffs or []),
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def caelan_at_lv_14_rested(gm_client, roster):
    """PATCH Sir Caelan to Paladin Lv 14 + long-rest him so the
    cleansing-touch resource is fresh. Restore Lv 6 in teardown.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 14},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    yield caelan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 6},
    )


async def test_use_cleansing_touch_happy_path(
    gm_client, caelan_at_lv_14_rested, roster,
):
    """Caelan @ Lv 14 touches Pip (who has a synthetic charmed
    buff) → 200; charmed removed from Pip; resource decrements
    to 2/3.
    """
    caelan = caelan_at_lv_14_rested
    pip = roster["Pip Quickfingers"]
    cae_tok = f"tok_ct_cae_{caelan['id']}"
    pip_tok = f"tok_ct_pip_{pip['id']}"
    # Pip starts with a synthetic charmed buff that Caelan will end.
    pip_buffs = [{
        "key": "charmed", "name": "Charmed (test seed)",
        "icon": "💕", "duration_rounds": 100, "concentration": False,
        "source": "test-seed",
    }]
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"], buffs=pip_buffs),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cleansing_touch",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": pip_tok,
            "buff_key": "charmed",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["buff_key_removed"] == "charmed"
    assert data["uses_remaining"] == 2  # 3 → 2
    # Pip no longer has charmed.
    pip_keys = await _get_buff_keys(gm_client, pip["id"])
    assert "charmed" not in pip_keys


async def test_use_cleansing_touch_below_lv_14_409(gm_client, roster):
    """Caelan @ stock Lv 6 → 409 missing_feature (level gate)."""
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    cae_tok = f"tok_ct_lv6_cae_{caelan['id']}"
    pip_tok = f"tok_ct_lv6_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cleansing_touch",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": pip_tok,
            "buff_key": "charmed",
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_feature"


async def test_use_cleansing_touch_buff_not_found_409(
    gm_client, caelan_at_lv_14_rested, roster,
):
    """Target has no matching buff → 409 buff_not_found.
    Resource shouldn't decrement on the no-op.
    """
    caelan = caelan_at_lv_14_rested
    pip = roster["Pip Quickfingers"]
    cae_tok = f"tok_ct_nb_cae_{caelan['id']}"
    pip_tok = f"tok_ct_nb_pip_{pip['id']}"
    # Pip has no charmed buff.
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(pip_tok, pip["id"], name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cleansing_touch",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": pip_tok,
            "buff_key": "charmed",
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "buff_not_found"


async def test_use_cleansing_touch_target_not_found_404(
    gm_client, caelan_at_lv_14_rested,
):
    """Unknown target_combatant_id → 404 target_not_found."""
    caelan = caelan_at_lv_14_rested
    cae_tok = f"tok_ct_404_cae_{caelan['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cleansing_touch",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "bogus-target",
            "buff_key": "charmed",
        },
    )
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data.get("error") == "target_not_found"


async def test_use_cleansing_touch_missing_fields_400(gm_client):
    """Missing buff_key → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cleansing_touch",
        json={"character_id": 1, "target_combatant_id": "x"},
    )
    assert resp.status_code == 400, resp.text
