"""v2.99.162 — Subtle Spell metamagic (Sorcerer Lv 3+).

RAW (PHB p.102): "When you Cast a Spell, you can spend 1
sorcery point to cast it without any somatic or verbal
components." Counterspell (PHB p.228) requires "you see a
creature within 60 feet of you casting a spell" — without V/S
components, Counterspell becomes inapplicable.

Mirror of v2.99.159 Distant + v2.99.160 Twinned + v2.99.161
Extended pending-buff pattern. Completes the metamagic suite —
all 7 Sorcerer metamagics now have at least pending-buff
scaffolding + mechanical wiring for their primary RAW effect.

Tests:
  - happy path: declaring Subtle Spell costs 1 SP + installs
    the pending buff + broadcasts
  - the pending buff is consumed when /cast_spell fires + a
    "subtle consumed" broadcast emits naming counterspell_immune
  - not enough SP → 409
  - wrong class (non-Sorcerer) → 409
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
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
async def zara_rested(gm_client, roster):
    """Long-rest Zara so SP is fresh."""
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def test_subtle_costs_1_sp_and_installs_buff(
    gm_client, zara_rested,
):
    """Declaring Subtle Spell costs 1 SP + installs the pending
    buff. Endpoint return shape matches the other metamagic
    endpoints (sp_cost, sp_remaining, sp_max, cast_id).
    """
    zara = zara_rested
    zara_tok = f"tok_sub_install_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_subtle_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["sp_remaining"] == data["sp_max"] - 1
    assert "cast_id" in data
    keys = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-subtle-pending" in keys


async def test_subtle_pending_consumed_by_cast_spell(
    gm_client, gm_ws, zara_rested,
):
    """After declaring Subtle Spell, the next /cast_spell call
    consumes the pending buff + broadcasts a "subtle consumed"
    feature_used naming the counterspell_immune flag.
    """
    zara = zara_rested
    zara_tok = f"tok_sub_consume_{zara['id']}"
    await _seed_battle(gm_client, [
        _mkc(zara_tok, zara["id"], name=zara["name"]),
    ])
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_subtle_spell",
        json={"character_id": zara["id"]},
    )
    assert arm.status_code == 200, arm.text
    pre = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-subtle-pending" in pre
    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 0,
            "override": True,
        },
    )
    assert cast.status_code in (200, 400, 409), cast.text
    post = await _get_buff_keys(gm_client, zara["id"])
    assert "metamagic-subtle-pending" not in post
    # Verify the "subtle consumed" broadcast fired.
    import asyncio as _asy
    await _asy.sleep(0.2)
    msgs = gm_ws.buffered("feature_used")
    consumed = [
        m for m in msgs
        if (m.get("data") or {}).get("source") == "metamagic-subtle-spell-consumed"
    ]
    assert consumed, (
        f"expected feature_used(source=metamagic-subtle-spell-consumed); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )
    assert (consumed[0].get("data") or {}).get("counterspell_immune") is True


async def test_subtle_not_enough_points(gm_client, zara_rested):
    """Drain Zara's SP via Empowered (5 SP pool), then Subtle
    returns 409 not_enough_points.
    """
    zara = zara_rested
    for _ in range(5):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_empowered_spell",
            json={"character_id": zara["id"]},
        )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_subtle_spell",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "not_enough_points"


async def test_subtle_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_metamagic_subtle_spell",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"
