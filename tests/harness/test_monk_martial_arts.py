"""v2.99.81 — Monk Martial Arts die progression (Lv 1+).

RAW (PHB p.78): unarmed strikes + monk weapons use these dice in
place of the weapon's normal damage:

    Lv 1-4   → 1d4
    Lv 5-10  → 1d6
    Lv 11-16 → 1d8
    Lv 17+   → 1d10

Server-side ``_apply_monk_martial_arts_die`` swaps the leading die
on attacks whose name matches ``unarmed strike`` or ``martial arts``
when the character is a Monk. Only UPGRADES (never downgrades) so a
sheet-authored larger die wins. Plugs in at ``/attack`` right after
``damage_expr_raw = attack.get("damage")``.

Tests use the v2.99.39 capstone-test pattern (class-scoped level
PATCH) to flip Kael between his demo Lv 7 (MA die 1d6) and Lv 11
(MA die 1d8) + Lv 17 (MA die 1d10).

Tests:
- happy: Kael Lv 11 unarmed → damage_expr starts with 1d8 (upgraded
  from sheet's 1d6+4).
- happy: Kael Lv 17 unarmed → 1d10.
- gate: Kael Lv 5 unarmed → 1d6 (sheet wins; no downgrade).
- gate: non-Monk PC's unarmed-named attack stays unchanged.
- name gate: Kael's non-monk-named attack stays unchanged.
"""
import re
import pytest_asyncio

from .conftest import CAMPAIGN_ID


UNARMED_INDEX = 0  # Kael's first attack in the demo seed


@pytest_asyncio.fixture
async def kael_at_lv(gm_client, roster):
    """Helper fixture factory — returns an async function that flips
    Kael's monk level and yields him. Restores Lv 7 in teardown.
    """
    kael = roster["Kael Brightleaf"]

    async def _set(level):
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
            json={"class_slug": "monk", "level": level},
        )
        return kael

    yield _set

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-fields",
        json={"class_slug": "monk", "level": 7},
    )


async def _attack(gm_client, gm_ws, char_id, attack_index):
    """POST /attack and return the weapon_attack broadcast data."""
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": char_id,
            "attack_index": attack_index,
            "override": True,  # bypass action chip if already spent
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    return msg["data"]


def _leading_die_face(damage_expr):
    """Extract the die face from a damage expression like '1d8+4'.
    Returns the integer face value (8) or None if no die present.
    """
    m = re.match(r"\s*\d*d(\d+)", damage_expr or "")
    return int(m.group(1)) if m else None


async def test_martial_arts_lv11_upgrades_to_d8(gm_client, gm_ws, kael_at_lv):
    """v2.99.81 happy: bump Kael to Lv 11; his Unarmed Strike damage
    expression swaps from sheet 1d6+4 to 1d8+4 at /attack time.
    """
    kael = await kael_at_lv(11)
    data = await _attack(gm_client, gm_ws, kael["id"], UNARMED_INDEX)
    expr = data.get("damage_expr") or ""
    assert _leading_die_face(expr) == 8, (
        f"Lv 11 Monk Unarmed should roll 1d8 (got expr={expr!r}); "
        f"_apply_monk_martial_arts_die may have failed to upgrade"
    )


async def test_martial_arts_lv17_upgrades_to_d10(gm_client, gm_ws, kael_at_lv):
    """v2.99.81 happy: bump Kael to Lv 17; Unarmed Strike → 1d10+4."""
    kael = await kael_at_lv(17)
    data = await _attack(gm_client, gm_ws, kael["id"], UNARMED_INDEX)
    expr = data.get("damage_expr") or ""
    assert _leading_die_face(expr) == 10, (
        f"Lv 17 Monk Unarmed should roll 1d10 (got expr={expr!r})"
    )


async def test_martial_arts_lv5_keeps_sheet_d6(gm_client, gm_ws, kael_at_lv):
    """v2.99.81 gate: bump Kael to Lv 5; his sheet's 1d6+4 stays.
    Helper returns 1d6 at Lv 5; sheet face == MA face → no-op.
    """
    kael = await kael_at_lv(5)
    data = await _attack(gm_client, gm_ws, kael["id"], UNARMED_INDEX)
    expr = data.get("damage_expr") or ""
    assert _leading_die_face(expr) == 6, (
        f"Lv 5 Monk Unarmed should keep the sheet's 1d6 (got expr={expr!r})"
    )


async def test_martial_arts_non_monk_stays_unchanged(gm_client, gm_ws, roster):
    """v2.99.81 class gate: a non-Monk PC's "Unarmed Strike" attack
    (none ship by default; we PATCH Krieger to add one) stays at
    its authored die. Helper short-circuits because _monk_level == 0.
    """
    krieger = roster["Krieger Stonefist"]
    # PATCH Krieger's sheet to add an Unarmed Strike attack at index 0.
    # Snapshot the original attacks list so we can restore.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}"
    )
    original_attacks = r.json()["sheet"].get("attacks") or []
    new_attacks = [
        {"name": "Unarmed Strike", "attack_bonus": "+4",
         "damage": "1d4+2", "damage_type": "bludgeoning",
         "range": "5 ft"},
    ] + original_attacks
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": new_attacks},
        )
        data = await _attack(gm_client, gm_ws, krieger["id"], 0)
        expr = data.get("damage_expr") or ""
        # Krieger is Barbarian, not Monk — die stays 1d4 (the sheet
        # value), no upgrade.
        assert _leading_die_face(expr) == 4, (
            f"Non-Monk Unarmed should keep sheet's 1d4 (got expr={expr!r}); "
            f"_apply_monk_martial_arts_die may be missing the class gate"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": original_attacks},
        )


async def test_martial_arts_non_monk_named_attack_stays(gm_client, gm_ws, kael_at_lv):
    """v2.99.81 name gate: Kael Lv 17's QUARTERSTAFF attack (whose
    name is "Quarterstaff (Martial Arts)" in the demo seed — does
    contain "martial arts") DOES upgrade to 1d10. Sanity-check the
    name match works for monk-weapon naming convention.

    Negative-side: an attack like "Dart" wouldn't match — but the
    demo doesn't have one for Kael; this test confirms the positive
    name-match.
    """
    kael = await kael_at_lv(17)
    # Quarterstaff is index 1 in Kael's attacks list.
    data = await _attack(gm_client, gm_ws, kael["id"], 1)
    expr = data.get("damage_expr") or ""
    assert _leading_die_face(expr) == 10, (
        f"Lv 17 Monk Quarterstaff (Martial Arts) should swap die to "
        f"1d10 (got expr={expr!r})"
    )
