"""/api/campaign/{cid}/attack — weapon attack endpoint tests.

Coverage in this Phase 1 vertical slice:
  - Pip's Shortsword (PC, attack_index 0)
  - Pip's Dagger (PC, attack_index 1)
  - Tavik's Warhammer (PC, attack_index 0)
  - 404 on unknown attack_index

Phase 1.5 will add: bandit / monster strikes via /roll (separate path),
save-DC-based attacks (Sacred Flame), over-budget gate parametrization.
"""
from .conftest import CAMPAIGN_ID


async def test_attack_pip_shortsword(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["attack_name"] == "Shortsword"
    # 1d20+6 produces a total between 7 and 26.
    assert 7 <= data["attack_total"] <= 26
    # Breakdown format: "1d20[N]=N 6  =>  total". Just check the d20
    # part landed and the total is consistent.
    assert "1d20" in data["attack_breakdown"]
    # Damage: 1d6+3 → 4-9 non-crit; crit doubles to 2d6+3 → 5-15.
    # v2.49.242: relax for crit case (audit pass from v2.49.240 notes).
    assert 4 <= data["damage_total"] <= 15
    assert data["damage_type"] == "piercing"

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["attack_name"] == "Shortsword"
    assert msg["data"]["caster_char_name"] == "Pip Quickfingers"
    assert msg["data"]["damage_type"] == "piercing"
    # over_budget can be True or False depending on whether Pip's
    # action chip was already burnt from a prior test or run. The
    # realtime hub keeps battle state in-memory across requests, so
    # the chip persists until init advances. Phase 1.5 adds per-test
    # battle-state reset; for now we just assert the field is present
    # and a bool.
    assert "over_budget" in msg["data"]
    assert isinstance(msg["data"]["over_budget"], bool)


async def test_attack_pip_dagger(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 1, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Dagger (thrown)"
    # 1d4+3 → 4-7 non-crit; crit doubles to 2d4+3 → 5-11.
    assert 4 <= data["damage_total"] <= 11

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["range"] == "20/60 ft"


async def test_attack_tavik_warhammer(gm_client, gm_ws, roster):
    """The v2.7.3 regression target: clicking Tavik's Warhammer should
    fire a weapon_attack broadcast that produces a roll toast."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": tavik["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Warhammer"
    # 1d8+2 → 3-10 non-crit; crit doubles to 2d8+2 → 4-18.
    assert 3 <= data["damage_total"] <= 18
    assert data["damage_type"] == "bludgeoning"

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["attack_name"] == "Warhammer"
    assert msg["data"]["caster_char_name"] == "Brother Tavik Stonebrow"
    # The broadcast must carry both totals + breakdowns so the
    # roll_toast.js listener has what it needs to fire the toast.
    assert msg["data"]["attack_total"] is not None
    assert msg["data"]["attack_breakdown"]
    assert msg["data"]["damage_total"] is not None
    assert msg["data"]["damage_breakdown"]


async def test_attack_invalid_index(gm_client, roster):
    """Out-of-range attack_index returns 404."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 999, "override": True},
    )
    assert resp.status_code == 404


async def test_attack_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"attack_index": 0},
    )
    assert resp.status_code == 400


async def test_attack_sneak_attack_uplift(gm_client, gm_ws, roster):
    """v2.16.0: Pip swings his Shortsword AND declares Sneak Attack.
    Response carries bonus_damage_label + bonus_damage_total; broadcast
    surfaces them on a separate line so the chat can render the
    attribution. No spell slot consumed (Sneak Attack isn't slot-fueled).

    v2.51.6: Pip bumped Lv 5 → Lv 7 to land Rogue Evasion; her Sneak
    Attack die scales `ceil(7/2) = 4d6` (was 3d6 at Lv 5). Non-crit
    range = [4, 24]; crit doubles dice to 8d6 → [8, 48].
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "bonus_damage": "4d6",
            "bonus_damage_label": "Sneak Attack",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["bonus_damage_label"] == "Sneak Attack"
    assert data["bonus_damage_total"] is not None
    # 4d6 non-crit range = [4, 24]; crit doubles to 8d6 → [8, 48].
    assert 4 <= data["bonus_damage_total"] <= 48
    assert "4d6" in data["bonus_damage_breakdown"]
    assert data["slot_spent_class"] == ""
    assert data["slot_spent_level"] == 0

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["bonus_damage_label"] == "Sneak Attack"
    assert msg["data"]["bonus_damage_total"] == data["bonus_damage_total"]
    assert msg["data"]["bonus_damage_expr"] == "4d6"


async def test_attack_divine_smite_spends_slot(gm_client, gm_ws, roster):
    """v2.16.0: Caelan swings his Longsword AND declares Divine Smite
    (L1 slot → 2d8 radiant). Response: bonus_damage_total in 2-16,
    slot_spent_class='paladin', slot_spent_level=1. Caelan's paladin
    L1 slot pool decrements by 1 (was 4, becomes 3).

    Long-rests Caelan first to ensure the slot pool is full + reverts
    any prior depletion from earlier tests in the session.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    # Refill slots via long rest.
    refill = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    assert refill.status_code == 200, refill.text
    gm_ws.mark()  # discard the long-rest broadcasts

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": 0,
            "bonus_damage": "2d8",
            "bonus_damage_label": "Divine Smite",
            "spend_spell_slot": {"class_slug": "paladin", "level": 1},
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["bonus_damage_label"] == "Divine Smite"
    # 2d8 non-crit range = [2, 16]; on a crit `_double_dice_for_crit`
    # widens the bonus to 4d8 → [4, 32]. v2.49.240 relaxed the cap
    # after CI caught the crit case (assert 25 <= 16 fired in the
    # 2026-05-25 run). Same shape as the v2.49.233 empowered + v2.49.235
    # multi-target assertion fixes.
    assert 2 <= data["bonus_damage_total"] <= 32
    assert data["slot_spent_class"] == "paladin"
    assert data["slot_spent_level"] == 1

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["bonus_damage_label"] == "Divine Smite"
    assert msg["data"]["slot_spent_class"] == "paladin"
    assert msg["data"]["slot_spent_level"] == 1


async def test_attack_divine_smite_no_slot(gm_client, gm_ws, roster):
    """Deplete all of Caelan's L1 slots, then attempt Divine Smite at L1
    → 409 with error="no_slot". The base attack does NOT fire (server
    aborts before rolling damage).

    Drain pattern: deplete via repeated /attack-with-smite calls until
    the next call returns 409. The previous test consumed 1 slot from
    a full pool of 4 (Lv 5 Paladin); we don't long-rest at the start so
    this test runs against whatever the prior test left behind. The drain
    loop handles the unknown starting count.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    max_attempts = 6  # Paladin Lv 5 has 4 L1 slots + safety margin
    for _ in range(max_attempts):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": caelan["id"],
                "attack_index": 0,
                "bonus_damage": "2d8",
                "bonus_damage_label": "Divine Smite",
                "spend_spell_slot": {"class_slug": "paladin", "level": 1},
                "override": True,
            },
        )
        if resp.status_code == 409:
            body = resp.json()
            assert body.get("error") == "no_slot"
            assert body.get("class_slug") == "paladin"
            assert body.get("level") == 1
            return
        assert resp.status_code == 200, resp.text
    raise AssertionError(
        f"Expected 409 no_slot within {max_attempts} attempts but the "
        "endpoint kept returning 200 — the no-slot guard may have regressed."
    )


async def test_attack_spend_slot_missing_class(gm_client, roster):
    """spend_spell_slot without class_slug returns 400."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": 0,
            "spend_spell_slot": {"level": 1},  # missing class_slug
            "override": True,
        },
    )
    assert resp.status_code == 400


async def test_attack_divine_smite_undo_refunds_slot(gm_client, gm_ws, roster):
    """v2.99.464 — the chat-card ↶ Undo now refunds the Divine Smite spell
    slot, not just the damage. Caelan long-rests (paladin L1 → 4/0), swings
    with a L1 smite (used → 1), then /undo_attack_damage with the attack id
    → a spell_slot_update broadcasts the paladin L1 slot's used back to 0.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    refill = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    assert refill.status_code == 200, refill.text

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caelan["id"], "attack_index": 0,
              "bonus_damage": "2d8", "bonus_damage_label": "Divine Smite",
              "spend_spell_slot": {"class_slug": "paladin", "level": 1},
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slot_spent_class"] == "paladin"
    assert data["slot_spent_level"] == 1
    attack_id = data["id"]

    gm_ws.mark()
    u = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": attack_id},
    )
    assert u.status_code == 200, u.text
    ssu = await gm_ws.wait_for("spell_slot_update", timeout=2.0)
    assert ssu["data"]["class_slug"] == "paladin"
    assert ssu["data"]["level"] == 1
    assert ssu["data"]["used"] == 0  # smite slot refunded (1 → 0)


async def test_attack_assassinate_auto_crit_vs_surprised(gm_client, gm_ws, roster):
    """v2.131.0 — Assassin Rogue Lv 3+ Assassinate: any hit against a
    surprised creature is a critical hit. Pip is seeded as Thief, so the
    test PATCH-swaps his subclass to "Assassin" (Lv 3 is already
    satisfied), fires an attack with `target_surprised: true`, asserts
    is_crit on the broadcast, then restores Thief. Subclass-gated so a
    non-Assassin caller can't force the crit."""
    pip = roster["Pip Quickfingers"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_subclass = sheet.get("subclass") or ""
    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"subclass": "Assassin"},
    )
    assert patch.status_code == 200, patch.text
    try:
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,           # Shortsword
                "target_surprised": True,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        msg = await gm_ws.wait_for("weapon_attack")
        d = msg["data"]
        assert d["attack_name"] == "Shortsword"
        assert d.get("is_crit") is True, (
            f"Assassin Lv 3 + target_surprised=true should auto-crit; "
            f"is_crit={d.get('is_crit')!r}"
        )
        # Crit doubles the weapon dice (RAW): Shortsword 1d6+3 → 2d6+3,
        # so damage range becomes [5, 15] (vs [4, 9] non-crit).
        assert 5 <= d["damage_total"] <= 15, (
            f"crit-doubled damage out of expected 2d6+3 range; got "
            f"{d['damage_total']}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"subclass": orig_subclass},
        )


