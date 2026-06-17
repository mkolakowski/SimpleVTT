"""v2.157.1 — Pre-click condition warning pill on the mini-sheet abilities header.

When a PC carries a condition buff that drives the v2.152.0–v2.157.0
adv/dis or auto-fail automation (Poisoned / Frightened / Restrained /
Blinded / Prone / Paralyzed / Stunned / Unconscious / Petrified /
Invisible), the mini-sheet's abilities header renders a small
"⚠ Conditions" pill with a tooltip listing each active condition +
its impact on d20 rolls. The pill is server-rendered from
``_mini_sheet_card.html`` so it shows up on the initial page load
AND any time the WS battle_update broadcast re-renders the mini-sheet.

Tests:
  - Pip in battle with a Poisoned buff → tabletop page response
    contains the warning pill near Pip's mini-sheet abilities header,
    with "Poisoned" in the tooltip.
  - Control: Pip with no condition buffs → no warning pill in his
    mini-sheet block.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0, "round": 1, "active": True,
        },
    )


def _find_char_detail(html: str, char_name: str) -> str:
    """Return Pip's .char-detail HTML slice from the tabletop page."""
    marker = f'class="mini-header-name">{char_name}'
    idx = html.find(marker)
    assert idx >= 0, f".char-detail block for {char_name!r} not found"
    start = html.rfind('<div class="char-detail"', 0, idx)
    assert start >= 0
    end = min(start + 60000, len(html))
    return html[start:end]


async def test_poisoned_pc_mini_sheet_shows_warning_pill(
    gm_client, roster,
):
    """Pip carries a Poisoned buff (mirrored to sheet._buffs_active via
    the v2.97.30 PUT /battle hook) → the abilities header in his
    mini-sheet renders a ``.mini-ab-cond-warn`` pill with "Poisoned"
    in the tooltip text."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        {"id": pip_cid, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [{"key": "poisoned", "name": "Poisoned"}],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    pip_html = _find_char_detail(resp.text, pip["name"])
    assert "mini-ab-cond-warn" in pip_html, (
        "Expected the abilities header to carry the .mini-ab-cond-warn "
        "pill when Pip has the Poisoned buff active."
    )
    # The tooltip should call out the Poisoned condition name + the
    # RAW impact phrase from the template's `_cond_impact_map`.
    assert "Poisoned" in pip_html
    assert "disadvantage on attacks + ability checks" in pip_html, (
        "Expected the tooltip to surface Poisoned's RAW impact text."
    )


async def test_charmed_pc_mini_sheet_shows_charmer_block_warning(
    gm_client, roster,
):
    """v2.401.0 — Pip carries a Charmed buff → the abilities header pill
    surfaces the new "cannot attack charmer or target charmer with harmful
    spells" impact string that mirrors the v2.390.0/v2.391.0 gate. Covers
    the post-v2.385.0–v2.391.0 enforcement sweep being made visible
    through the same warning-pill UI the d20-adv/dis conditions use."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        {"id": pip_cid, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [{"key": "charmed", "name": "Charmed"}],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    pip_html = _find_char_detail(resp.text, pip["name"])
    assert "mini-ab-cond-warn" in pip_html, (
        "Expected the abilities header to carry the .mini-ab-cond-warn "
        "pill when Pip has the Charmed buff active."
    )
    assert "Charmed" in pip_html
    assert "cannot attack charmer or target charmer with harmful spells" in pip_html, (
        "Expected the tooltip to surface the v2.401.0 Charmed impact text "
        "mirroring the v2.390.0/v2.391.0 attack/cast_spell gate."
    )
    # Label broadened in v2.401.0 since Charmed/Grappled/Incapacitated
    # gate actions rather than d20 rolls — assert the new label so a
    # regression that reverts to "affecting d20 rolls" gets caught.
    assert "Active conditions affecting actions or d20 rolls" in pip_html


async def test_grappled_pc_mini_sheet_shows_speed_zero_warning(
    gm_client, roster,
):
    """v2.401.0 — Grappled buff surfaces the "speed reduced to 0" impact
    in the warning pill, matching the v2.99.112 + v2.389.0 enforcement."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        {"id": pip_cid, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [{"key": "grappled", "name": "Grappled"}],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    pip_html = _find_char_detail(resp.text, pip["name"])
    assert "mini-ab-cond-warn" in pip_html
    assert "Grappled" in pip_html
    assert "speed reduced to 0" in pip_html


async def test_incapacitated_pc_mini_sheet_shows_action_gate_warning(
    gm_client, roster,
):
    """v2.401.0 — Incapacitated buff surfaces the "cannot take actions,
    bonus actions, or reactions" impact, matching the v2.385.0–v2.388.0
    /attack + /cast_spell + /use_feature gate sweep."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        {"id": pip_cid, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [{"key": "incapacitated", "name": "Incapacitated"}],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    pip_html = _find_char_detail(resp.text, pip["name"])
    assert "mini-ab-cond-warn" in pip_html
    assert "Incapacitated" in pip_html
    assert "cannot take actions, bonus actions, or reactions" in pip_html


async def test_clean_pc_mini_sheet_omits_warning_pill(
    gm_client, roster,
):
    """Control: Pip with no condition buffs in battle → the
    .mini-ab-cond-warn pill is NOT rendered. The render gate is
    ``{% if _ab_warn_ns.parts %}`` so an empty list omits the markup
    entirely."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        {"id": pip_cid, "char_id": pip["id"], "name": pip["name"],
         "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0}},
    ])
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    pip_html = _find_char_detail(resp.text, pip["name"])
    assert "mini-ab-cond-warn" not in pip_html, (
        "Pip with no condition buffs should NOT render the warning pill."
    )
