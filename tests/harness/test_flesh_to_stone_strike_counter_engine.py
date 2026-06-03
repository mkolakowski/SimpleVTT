"""v2.99.136 — Flesh to Stone strike-counter engine wiring tests.

v2.99.135 stamped the strike-counter fields on the Restrained buff.
v2.99.136 wires them into `_resolve_repeated_save_for_buff`:
  - Increment success_count on pass / failure_count on fail
  - Suppress the default "drop on pass" behavior until threshold
  - Transition Restrained → Petrified on 3 failures
  - Drop on 3 successes (existing logic fires)

Determinism strategy: install a synthetic FtS Restrained buff
on Krieger pre-loaded with success_count=2 OR failure_count=2.
Trigger /use_repeated_save with Krieger's CON score swung high
(PATCH abilities.CON to 30 → save passes always) or low
(PATCH CON to 1 + repeated_save_dc high → save fails always).
After one save, the 3rd strike fires.

Tests:
  - 3 successes drops the Restrained buff
  - 3 failures drops Restrained + installs Petrified
  - 1 success + 1 failure keeps the buff with counts (1, 1)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 75, "hp_max": 75,
        "speed_walk": speed_walk,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _fts_restrained_buff(source_char_id, source_name, base_speed,
                         dc, success_count=0, failure_count=0):
    """Synthetic FtS Restrained buff matching v2.99.135 install
    output. Pre-loaded counters let tests trigger threshold events
    deterministically.
    """
    return {
        "key": "restrained",
        "name": "Restrained (Flesh to Stone)",
        "icon": "🪨",
        "duration_rounds": 10,
        "concentration": True,
        "source": "flesh-to-stone-spell",
        "source_char_id": source_char_id,
        "source_char_name": source_name,
        "effects": {"speed_reduction_ft": base_speed},
        "raw_effects": ["Restrained — Flesh to Stone stage 1"],
        "repeated_save_ability": "STR",
        "repeated_save_dc": dc,
        "strike_counter": True,
        "success_count": success_count,
        "failure_count": failure_count,
        "strike_threshold": 3,
    }


async def _get_buffs(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("buffs") or []


async def _patch_krieger_str_score(gm_client, krieger_id, score):
    """PATCH Krieger's STR score so STR save passes deterministically
    (high) or fails deterministically (low). The buff's
    repeated_save_ability="STR" so STR save modifier dictates the
    roll outcome. Score 30 = mod +10; vs DC 1 = always passes.
    Score 1 = mod -5; vs DC 30 = always fails.
    """
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger_id}/buffs",
    )
    # We don't have a raw-sheet endpoint; PATCH abilities directly.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger_id}/sheet-fields",
        json={"abilities": {"STR": score, "DEX": 14, "CON": 16,
                            "INT": 10, "WIS": 10, "CHA": 10}},
    )


@pytest_asyncio.fixture
async def krieger_with_fts_restrained(gm_client, roster):
    """PATCH Krieger to a known ability spread. Restore on teardown.
    The Restrained-buff seed is per-test.
    """
    krieger = roster["Krieger Stonefist"]
    # Restore Krieger's stock abilities on teardown.
    # Stock: STR 17, DEX 14, CON 16, INT 8, WIS 12, CHA 10 (approx).
    yield krieger
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"abilities": {"STR": 17, "DEX": 14, "CON": 16,
                            "INT": 8, "WIS": 12, "CHA": 10}},
    )


async def test_three_successes_drops_restrained(
    gm_client, krieger_with_fts_restrained, roster,
):
    """Pre-load success_count=2. PATCH Krieger STR very high
    (auto-pass). Trigger /use_repeated_save → success_count
    reaches 3 → Restrained drops.
    """
    krieger = krieger_with_fts_restrained
    thalindra = roster["Thalindra Moonwhisper"]
    # Set Krieger's STR mod to +10 (score 30) and the buff's DC to
    # 1 so the STR save deterministically passes.
    await _patch_krieger_str_score(gm_client, krieger["id"], 30)
    kr_tok = f"tok_fts_eng_succ_kr_{krieger['id']}"
    seed_buff = _fts_restrained_buff(
        source_char_id=thalindra["id"],
        source_name=thalindra["name"],
        base_speed=40, dc=1, success_count=2, failure_count=0,
    )
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=40, buffs=[seed_buff]),
    ])
    # Trigger the save.
    save_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": krieger["id"], "buff_key": "restrained"},
    )
    assert save_resp.status_code == 200, save_resp.text
    # Re-read Krieger's buffs. Restrained should be gone.
    buff_keys = {(b or {}).get("key") for b in await _get_buffs(gm_client, krieger["id"])}
    assert "restrained" not in buff_keys, (
        f"3 successes should drop Restrained; got keys={buff_keys}"
    )
    # Petrified should NOT be present (success path ends the spell,
    # doesn't transition).
    assert "petrified" not in buff_keys, buff_keys


async def test_three_failures_transitions_to_petrified(
    gm_client, krieger_with_fts_restrained, roster,
):
    """Pre-load failure_count=2. PATCH Krieger STR very low (auto-
    fail). Trigger /use_repeated_save → failure_count reaches 3 →
    Restrained drops + Petrified installs.
    """
    krieger = krieger_with_fts_restrained
    thalindra = roster["Thalindra Moonwhisper"]
    # Score 1 → mod -5. DC 30 → impossible roll.
    await _patch_krieger_str_score(gm_client, krieger["id"], 1)
    kr_tok = f"tok_fts_eng_fail_kr_{krieger['id']}"
    seed_buff = _fts_restrained_buff(
        source_char_id=thalindra["id"],
        source_name=thalindra["name"],
        base_speed=40, dc=30, success_count=0, failure_count=2,
    )
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=40, buffs=[seed_buff]),
    ])
    save_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": krieger["id"], "buff_key": "restrained"},
    )
    assert save_resp.status_code == 200, save_resp.text
    buff_keys = {(b or {}).get("key") for b in await _get_buffs(gm_client, krieger["id"])}
    assert "restrained" not in buff_keys, (
        f"3 failures should drop Restrained; got keys={buff_keys}"
    )
    assert "petrified" in buff_keys, (
        f"3 failures should install Petrified; got keys={buff_keys}"
    )


async def test_first_save_increments_counter_only(
    gm_client, krieger_with_fts_restrained, roster,
):
    """No pre-load. Trigger one save with a low DC (auto-pass).
    success_count becomes 1, failure stays 0, buff stays Restrained.
    """
    krieger = krieger_with_fts_restrained
    thalindra = roster["Thalindra Moonwhisper"]
    await _patch_krieger_str_score(gm_client, krieger["id"], 30)
    kr_tok = f"tok_fts_eng_one_kr_{krieger['id']}"
    seed_buff = _fts_restrained_buff(
        source_char_id=thalindra["id"],
        source_name=thalindra["name"],
        base_speed=40, dc=1, success_count=0, failure_count=0,
    )
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=40, buffs=[seed_buff]),
    ])
    save_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": krieger["id"], "buff_key": "restrained"},
    )
    assert save_resp.status_code == 200, save_resp.text
    buffs = await _get_buffs(gm_client, krieger["id"])
    restrained = next(
        (b for b in buffs if b.get("key") == "restrained"), None,
    )
    assert restrained is not None, f"buff should stay; got {buffs}"
    assert restrained.get("success_count") == 1, restrained
    assert restrained.get("failure_count") == 0, restrained
