"""v2.99.323 — Swords College Bard: Blade Flourish (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #5. RAW XGE p.16: on Attack
action walking speed +10 ft until end of turn. On weapon
hit, expend 1 BI use to apply one Flourish:
- Defensive: +BI damage + AC until next turn.
- Slashing: +BI damage to nearby creature within 5 ft of target.
- Mobile: +BI damage + push target 5 ft + free reaction-move.

Once per turn.

v1 announce-only — BI roll + applied bonus GM-tracked.

Lyra Lv 6 → walking +10, choice of flourish.

Tests:
  - Lv 3+ happy default Defensive → walking +10, flourish "defensive".
  - flourish="slashing" passthrough.
  - flourish="mobile" passthrough.
  - Wrong subclass → 409.
  - Swords Lv 2 → 409.
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


def _bf_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "blade-flourish"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_swords(gm_client, roster):
    """PATCH Lyra to College of Swords."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Swords"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_bf_happy_lv6_defensive(
    gm_client, gm_ws, lyra_swords,
):
    """Lv 6 Swords default Defensive → walking +10."""
    lyra = lyra_swords
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "defensive"
    assert data["walking_speed_bonus_ft"] == 10
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _bf_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_bf_slashing(
    gm_client, lyra_swords,
):
    """flourish='slashing' passes through."""
    lyra = lyra_swords
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "slashing"


async def test_use_bf_mobile(
    gm_client, lyra_swords,
):
    """flourish='mobile' passes through."""
    lyra = lyra_swords
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "mobile"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "mobile"


async def test_bf_installs_speed_bonus_buff(
    gm_client, lyra_swords,
):
    """v2.667.0 — Phase 8: Blade Flourish's +10 ft walking-speed bonus is now
    mechanized (was announce-only). Using the flourish installs a 1-round
    `blade-flourish-speed-active` buff carrying `effects.speed_bonus_ft: 10`,
    which the `effective_speed_walk` engine adds to the move cap (same
    substrate Longstrider uses). Applies regardless of the flourish option.

    Seeds a battle with Lyra because `_install_buff` requires an active battle
    (returns False otherwise); pre-clears the buff for order-independence."""
    lyra = lyra_swords
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_bf_{lyra['id']}", "char_id": lyra["id"],
                "name": lyra["name"], "initiative": 11,
                "hp_current": 40, "hp_max": 40, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": lyra["id"],
              "key": "blade-flourish-speed-active"},
    )
    # mobile flourish (no target) — proves the speed buff is flourish-agnostic.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "mobile"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("speed_buff_installed") is True
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/buffs"
    )).json().get("buffs", [])
    sp = next(
        (b for b in buffs if b.get("key") == "blade-flourish-speed-active"),
        None,
    )
    assert sp is not None, (
        f"blade-flourish-speed-active buff missing; got keys="
        f"{[b.get('key') for b in buffs]}"
    )
    assert (sp.get("effects") or {}).get("speed_bonus_ft") == 10
    # 1-round duration (until end of turn) — not a permanent passive.
    assert int(sp.get("duration_rounds") or 0) == 1
    assert sp.get("concentration") in (False, None)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": lyra["id"],
              "key": "blade-flourish-speed-active"},
    )


async def test_use_bf_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bf_level_gate(
    gm_client, roster,
):
    """Swords Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Swords", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


def _pc(cid, c, hp=30):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_bf_damage_with_target_applies_bonus(
    gm_client, gm_ws, lyra_swords, roster,
):
    """v2.146.0 — Phase 1 (shared damage half): when /use_blade_flourish
    is called with `target_combatant_id` + `damage_type`, the endpoint
    rolls the BI die server-side and applies it as bonus damage to the
    target via `_apply_damage_to_combatant`. Backward-compatible:
    without `target_combatant_id`, the endpoint stays announce-only.
    Lyra Lv 6 → 1d8. Resistance halving may fire on Pip's residual
    state (same pattern as v2.144.1's CI test); accept `applied` ∈
    `{rolled, rolled // 2}`."""
    lyra = lyra_swords
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_bf_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_bf_l_{lyra['id']}", lyra),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"],
              "flourish": "defensive",
              "target_combatant_id": pip_tok,
              "damage_type": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "defensive"
    assert data["die_size"] == 8     # Lv 6 → 1d8
    br = data.get("bonus_rolled")
    ba = data.get("bonus_applied")
    assert br is not None and 1 <= br <= 8, (
        f"BI die should roll 1-8; got {br}"
    )
    assert ba is not None and ba > 0
    assert ba in (br, br // 2), (
        f"applied should be rolled or halved (resistance); got "
        f"rolled={br}, applied={ba}"
    )


async def test_bf_damage_without_target_announce_only(
    gm_client, lyra_swords,
):
    """v2.146.0 — Without `target_combatant_id`, the endpoint stays
    announce-only (no BI die rolled, no damage applied). Backward-
    compatible with the v2.99.323 contract."""
    lyra = lyra_swords
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "defensive"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "defensive"
    assert data.get("bonus_rolled") is None
    assert data.get("bonus_applied") is None
    # v2.158.66 — Phase 2 fields stay zero/False when announce-only.
    assert data["defensive_ac_bonus"] == 0
    assert data["defensive_buff_installed"] is False


async def test_bf_defensive_installs_ac_buff(
    gm_client, gm_ws, lyra_swords, roster,
):
    """v2.158.66 — Phase 2 Defensive Flourish AC self-buff. When the
    flourish is "defensive" AND a BI die was rolled (target_combatant_id
    provided), the endpoint installs a 1-round
    `blade-flourish-defensive-active` buff on the bard with
    `effects.ac_bonus` matching the BI roll. Asserts: (a) response carries
    `defensive_ac_bonus == bonus_rolled` and `defensive_buff_installed
    is True`; (b) the feature_used broadcast surfaces the same; (c) a
    `buff_update` broadcast lands the buff on Lyra's combatant entry
    with the expected `effects.ac_bonus` and `key`."""
    lyra = lyra_swords
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_bfd_p_{pip['id']}"
    lyra_tok = f"tok_bfd_l_{lyra['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(lyra_tok, lyra),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"],
              "flourish": "defensive",
              "target_combatant_id": pip_tok,
              "damage_type": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    br = data.get("bonus_rolled")
    assert br is not None and 1 <= br <= 8, (
        f"BI die should roll 1-8; got {br}"
    )
    # Response surfaces the Phase 2 AC-buff fields.
    assert data["defensive_buff_installed"] is True
    assert data["defensive_ac_bonus"] == br, (
        f"defensive_ac_bonus should match bonus_rolled; "
        f"got ac={data['defensive_ac_bonus']}, rolled={br}"
    )

    # The feature_used broadcast carries the same Phase 2 fields so
    # the chat card can render the AC bonus alongside the damage.
    await asyncio.sleep(0.3)
    feats = _bf_broadcasts(gm_ws, lyra["id"])
    assert feats, "no feature_used(source=blade-flourish) broadcast fired"
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("defensive_buff_installed") is True
    assert feat_data.get("defensive_ac_bonus") == br

    # The buff_update broadcast carries the installed buff on Lyra's
    # combatant entry — `effects.ac_bonus` is what the
    # _read_target_ac walker (v2.97.39) sums into the bard's AC.
    # `_install_buff` keys the broadcast by `character_id` (not by
    # combatant id) because the install path looks up the combatant
    # via the PC's char_id under the hood.
    bu_msgs = [
        m for m in gm_ws.buffered("buff_update")
        if int((m.get("data") or {}).get("character_id") or 0) == int(lyra["id"])
    ]
    assert bu_msgs, (
        "no buff_update broadcast fired for Lyra's combatant after the "
        "defensive flourish"
    )
    last_buffs = (bu_msgs[-1].get("data") or {}).get("buffs") or []
    bf_entries = [
        b for b in last_buffs
        if b.get("key") == "blade-flourish-defensive-active"
    ]
    assert bf_entries, (
        f"blade-flourish-defensive-active not in Lyra's buffs; got "
        f"keys={[b.get('key') for b in last_buffs]}"
    )
    bf = bf_entries[-1]
    assert (bf.get("effects") or {}).get("ac_bonus") == br, (
        f"installed buff's effects.ac_bonus should match bonus_rolled; "
        f"got buff={bf}, rolled={br}"
    )
    assert bf.get("duration_rounds") == 1
    assert bf.get("concentration") is False


async def test_bf_slashing_does_not_install_ac_buff(
    gm_client, gm_ws, lyra_swords, roster,
):
    """v2.158.66 — Regression guard: the AC buff is gated on
    `flourish == "defensive"`. A Slashing Flourish with a target still
    rolls + applies BI damage to the secondary target, but MUST NOT
    install the defensive AC self-buff on the bard. Asserts: (a)
    response has `defensive_ac_bonus == 0` + `defensive_buff_installed
    is False`; (b) no `blade-flourish-defensive-active` buff appears
    in any buff_update broadcast for Lyra's combatant."""
    lyra = lyra_swords
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_bfs_p_{pip['id']}"
    lyra_tok = f"tok_bfs_l_{lyra['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(lyra_tok, lyra),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"],
              "flourish": "slashing",
              "target_combatant_id": pip_tok,
              "damage_type": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Damage half still fires for slashing (Phase 1).
    assert data["flourish"] == "slashing"
    assert data.get("bonus_rolled") is not None
    # Phase 2 AC buff stays off — it's defensive-only.
    assert data["defensive_ac_bonus"] == 0
    assert data["defensive_buff_installed"] is False

    await asyncio.sleep(0.3)
    bu_msgs = [
        m for m in gm_ws.buffered("buff_update")
        if int((m.get("data") or {}).get("character_id") or 0) == int(lyra["id"])
    ]
    for m in bu_msgs:
        buffs = (m.get("data") or {}).get("buffs") or []
        for b in buffs:
            assert b.get("key") != "blade-flourish-defensive-active", (
                "Slashing Flourish must NOT install the defensive AC "
                f"buff on Lyra; got buff={b}"
            )
