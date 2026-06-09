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
