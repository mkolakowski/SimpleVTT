"""Mislead — L5 illusion, Bard/Wizard.
Phase 2 #60 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.546.0 — RAW PHB p.260: "You become invisible at the same time that an
illusory double of you appears where you are standing." Self,
Concentration up to 1 hour. The invisibility half is mechanical — the
`mislead` buff carries `effects.invisible: True`, so the v2.514.0
target-side read makes attacks against the caster have disadvantage. The
double is GM-narrated; the concentration ride drops the buff when the
caster concentrates elsewhere.

Tests:
  - Self-cast installs a concentration `mislead` buff with
    `invisible: True` + `mislead_double: True` (600 rounds).
  - **Mechanical:** an attacker swinging at the misleading caster gets
    `target_invisible` disadvantage (control before the cast does not).
  - Concentration ride: casting Fly drops the mislead buff.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_ml_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": 40, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    thal = roster.get("Thalindra Moonwhisper")
    if thal:
        for key in ("mislead", "fly"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": thal["id"], "key": key},
            )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_mislead_installs_invisible_concentration_buff(gm_client, roster):
    """Self-cast → concentration `mislead` buff carrying invisible +
    mislead_double; response flags invisible + concentration."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mislead",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "mislead"
    assert body["invisible"] is True
    assert body["concentration"] is True
    assert body["duration_rounds"] == 600

    buffs = await _buffs(gm_client, thal["id"])
    ml = next((b for b in buffs if b.get("key") == "mislead"), None)
    assert ml is not None, f"buff missing: {buffs}"
    assert ml.get("concentration") is True
    eff = ml.get("effects") or {}
    assert eff.get("invisible") is True
    assert eff.get("mislead_double") is True


async def test_mislead_imposes_attack_disadvantage(gm_client, roster, bright_map):
    """An attacker swinging at the misleading (invisible) caster gets
    `target_invisible` disadvantage; the control swing before the cast
    does not.

    ``bright_map`` neutralizes inherited ambient darkness so the roll-state
    reflects the invisibility edge, not a can't-see cancellation (B16)."""
    thal = roster["Thalindra Moonwhisper"]
    pip = roster["Pip Quickfingers"]
    thal_tok = "tok_ml_caster"
    await _set_battle(gm_client, [
        _tok(thal, thal_tok, init=5),
        _tok(pip, "tok_ml_pip", init=20),
    ])

    # Control: no Mislead yet → no target_invisible.
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": thal_tok, "override": True},
    )
    assert a.status_code == 200, a.text
    assert "target_invisible" not in (a.json().get("roll_state_applied") or ""), (
        f"control should not be target_invisible; got {a.json().get('roll_state_applied')!r}"
    )

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mislead",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    a2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": thal_tok, "override": True},
    )
    assert a2.status_code == 200, a2.text
    assert "target_invisible" in (a2.json().get("roll_state_applied") or ""), (
        f"Mislead should impose target_invisible; got {a2.json().get('roll_state_applied')!r}"
    )


async def test_mislead_drops_on_new_concentration(gm_client, roster):
    """Concentration ride: casting Fly drops the Mislead buff."""
    thal = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, [_tok(thal)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mislead",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    assert any(b.get("key") == "mislead"
               for b in await _buffs(gm_client, thal["id"]))

    f = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_fly",
        json={"character_id": thal["id"]},
    )
    assert f.status_code == 200, f.text
    after = await _buffs(gm_client, thal["id"])
    assert not any(x.get("key") == "mislead" for x in after), after
    assert any(x.get("key") == "fly" for x in after), after


async def test_cast_mislead_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mislead",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "mislead" in r.json()["expected"].lower()


async def test_cast_mislead_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mislead",
        json={},
    )
    assert r.status_code == 400, r.text
