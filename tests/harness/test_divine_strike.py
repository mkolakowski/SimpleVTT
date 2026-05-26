"""v2.60.0 — Divine Strike (Life Domain Cleric Lv 8+).

RAW: "Once on each of your turns when you hit a creature with a
weapon attack, you can cause the attack to deal an extra 1d8
radiant damage to the target. When you reach 14th level, the
extra damage increases to 2d8."

Wired into `_compute_attack_auto_uplifts` in
`app/routes/tabletop_routes.py`. Cleric Lv 8+ with Life Domain
subclass + a target_combatant + the attacker's
`economy.divine_strike_used` flag not yet set → adds a `1d8 radiant`
uplift to the /attack response's `auto_uplifts` list. Marker
helper `_mark_divine_strike_used` flips the flag so subsequent
attacks on the same turn don't re-fire (mirror of Colossus Slayer).

Tests:
  - Tavik (Cleric Lv 8 Life Domain) attacks Krieger with Warhammer
    → /attack response carries a `divine-strike` uplift with
    `damage_type: "radiant"` and `expression: "1d8"`.
  - Once-per-turn lock: a second attack on the same turn doesn't
    re-fire (Divine Strike absent from auto_uplifts).
  - Negative control: Pip (Rogue, not Cleric) attacks → no divine-
    strike uplift fires.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_full(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_divine_strike_fires_on_first_weapon_hit(
    gm_client, tavik_full, roster,
):
    """Tavik attacks Krieger with Warhammer → /attack auto_uplifts
    carries a divine-strike entry with 1d8 radiant.
    """
    tavik = tavik_full
    krieger = roster["Krieger Stonefist"]
    tavik_tok = f"tok_ds_{tavik['id']}"
    krieger_tok = f"tok_ds_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"], hp_cur=50, hp_max=75),
    ])

    # Loop a few times in case the to-hit roll misses (Tavik's
    # Warhammer +5 vs Krieger AC 15 needs 10+ on the die; ~55% hit).
    fired = False
    for _ in range(8):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if not data.get("hit"):
            continue
        uplifts = data.get("auto_uplifts") or []
        ds = next((u for u in uplifts if u.get("source") == "divine-strike"), None)
        assert ds is not None, (
            f"expected divine-strike uplift in auto_uplifts on hit; got "
            f"uplifts={uplifts}"
        )
        assert ds.get("damage_type") == "radiant", ds
        assert ds.get("expression") == "1d8", ds
        assert ds.get("total", 0) >= 1 and ds.get("total", 0) <= 8, ds
        fired = True
        break
    assert fired, "Divine Strike did not fire after 8 attack attempts (all missed)"


async def test_divine_strike_locks_after_first_hit(
    gm_client, tavik_full, roster,
):
    """Tavik attacks Krieger twice on the same turn. Divine Strike
    fires on the first hit; the second attack on the same turn does
    NOT re-fire (RAW: once per turn).
    """
    tavik = tavik_full
    krieger = roster["Krieger Stonefist"]
    tavik_tok = f"tok_ds_{tavik['id']}"
    krieger_tok = f"tok_ds_{krieger['id']}"

    # Loop attacks until the first one hits (to set the flag), then
    # attack again on the same turn and assert no second divine-strike.
    first_hit_data = None
    for _ in range(8):
        await _seed_battle(gm_client, [
            _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
            _mkc(krieger_tok, krieger["id"], name=krieger["name"], hp_cur=50, hp_max=75),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        data = resp.json()
        if data.get("hit"):
            first_hit_data = data
            break
    assert first_hit_data is not None, "could not land a first-hit Warhammer in 8 tries"

    # Second attack on the same turn (no battle re-seed → flag persists).
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": tavik["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_tok,
            "override": True,
        },
    )
    data2 = resp2.json()
    uplifts2 = data2.get("auto_uplifts") or []
    ds2 = next((u for u in uplifts2 if u.get("source") == "divine-strike"), None)
    assert ds2 is None, (
        f"divine-strike should NOT fire a second time on the same turn; "
        f"got: {ds2}"
    )


async def test_divine_strike_skips_non_cleric(
    gm_client, roster,
):
    """Pip (Rogue) attacks Krieger → no divine-strike uplift fires.
    Cleric Lv 8+ Life Domain gate filters this out.
    """
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    pip_tok = f"tok_ds_{pip['id']}"
    krieger_tok = f"tok_ds_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_tok, pip["id"], name=pip["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"], hp_cur=50, hp_max=75),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_tok,
            "override": True,
        },
    )
    data = resp.json()
    uplifts = data.get("auto_uplifts") or []
    ds = next((u for u in uplifts if u.get("source") == "divine-strike"), None)
    assert ds is None, (
        f"divine-strike should NOT fire for a non-Cleric attacker; got: {ds}"
    )
