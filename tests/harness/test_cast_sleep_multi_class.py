"""Sleep on Bard / Sorcerer / Warlock spell lists.

v2.49.63 — closes the v2.49.58 filed "add Sleep to BSW lists" item.
RAW Sleep's spell_lists per the SRD JSON: ``bard``, ``sorcerer``,
``warlock``, ``wizard``. Pre-v2.49.63 only Thalindra (wizard) had
Sleep on her demo seed list; this commit ships Lyra (Bard), Zara
(Sorcerer), Magnus (Warlock) seed entries + a DB backfill so the
running demo carries them too. One harness test per class verifies
``/cast_sleep`` works with the matching ``class_slug``.

Magnus's slots are L3-only (Pact Magic, Warlock Lv 5) so his test
casts at L3 → 9d8 pool. The other two cast at L1 → 5d8.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


def _pc(char, tid_prefix: str, hp: int = 30):
    return {
        "id": f"{tid_prefix}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _bandit(tmpl, tid: str, hp: int = 5):
    return {
        "id": tid,
        "char_id": None,
        "token_template_id": tmpl["id"],
        "name": tmpl["name"],
        "initiative": 5,
        "hp_current": hp,
        "hp_max": max(hp, 11),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_cast_sleep_bard(gm_client, lyra_rested):
    """Lyra (Bard) casts Sleep at L1 → 5d8 pool, single 5-HP bandit
    always affected."""
    lyra = lyra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_bard"
    await _seed_battle(gm_client, [
        _pc(lyra, "tok_lyra"),
        _bandit(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": lyra["id"],
            "class_slug": "bard",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["class_slug"] == "bard"
    assert body["pool_expr"] == "5d8"
    assert len(body["affected"]) == 1
    assert body["affected"][0]["combatant_id"] == bandit_id


async def test_cast_sleep_sorcerer(gm_client, zara_rested):
    """Zara (Sorcerer) casts Sleep at L1 → 5d8 pool, single 5-HP bandit
    always affected."""
    zara = zara_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_sorc"
    await _seed_battle(gm_client, [
        _pc(zara, "tok_zara"),
        _bandit(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": zara["id"],
            "class_slug": "sorcerer",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_slug"] == "sorcerer"
    assert body["pool_expr"] == "5d8"
    assert len(body["affected"]) == 1


async def test_cast_sleep_warlock_l3(gm_client, magnus_rested):
    """Magnus (Warlock Lv 5) has only L3 slots (Pact Magic). Casts
    Sleep at L3 → 9d8 pool (5 + 2*2)."""
    magnus = magnus_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_wlk"
    await _seed_battle(gm_client, [
        _pc(magnus, "tok_magnus"),
        _bandit(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 3,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_slug"] == "warlock"
    assert body["slot_level"] == 3
    assert body["pool_expr"] == "9d8"  # 5 + 2 * (3-1)
    assert 9 <= body["pool_total"] <= 72
    assert len(body["affected"]) == 1
