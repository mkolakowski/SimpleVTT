"""v2.261.0 — Bracers of Archery (RAW DMG p.156, uncommon, attunement): while
worn, the wearer has proficiency with the longbow and shortbow and gains a +2
bonus to damage rolls on ranged attacks made with such weapons.

The +2 ranged-bow damage bonus rides the `bracers-of-archery` catalog payload
(`ranged_bow_damage_bonus: 2` + `requires_attunement: True`), sums in
`_equipped_item_effects` into a new `ranged_bow_damage_bonus` int (+
`ranged_bow_damage_bonus_sources`), and surfaces on `/sheet-json` as
`derived.ranged_bow_damage_bonus = {bonus, sources}`. At `/attack` time the
bonus is appended to the damage expression for a ranged "bow" weapon that
isn't a crossbow (RAW excludes crossbows). Attunement-gated: the per-payload
attunement check drops the bonus when worn-but-not-attuned. The proficiency
half is GM-narrated in v1.

Demo fixture: Rowan Quickbow (Ranger) wears it attuned — the demo's dedicated
archer; the bracers sit on his forearms, distinct from his Gauntlets of Ogre
Power (hands). His Longbow (attack_index 0, 1d8+4) gains the +2; his off-hand
Shortsword (attack_index 1, melee) does not.
"""
from .conftest import CAMPAIGN_ID

_BRACERS_SLUG = "bracers-of-archery"
_LONGBOW_INDEX = 0
_SHORTSWORD_INDEX = 1


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _attack(gm_client, char_id, attack_index):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": char_id,
            "attack_index": attack_index,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _flat_modifier_sum(breakdown: str) -> int:
    """Sum the flat (non-dice) modifier tokens in a damage breakdown.

    Breakdown format is ``<dice>[rolls]=<subtotal> <mod1> <mod2> ...  =>  <total>``.
    The first whitespace token is the dice subtotal (contains "="); the rest
    are flat integer modifiers. Crits double the *dice*, not these modifiers,
    so this is stable across crit/non-crit and across random die faces.
    """
    left = (breakdown or "").split("=>")[0].strip()
    toks = left.split()
    total = 0
    for t in toks[1:]:
        if t.lstrip("+-").isdigit():
            total += int(t)
    return total


async def test_bracers_of_archery_exposes_derived(gm_client, roster):
    """Happy path: Rowan's `/sheet-json` reports `derived.ranged_bow_damage_bonus`
    of +2 with the bracers named in its sources."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    rbdb = (data.get("derived") or {}).get("ranged_bow_damage_bonus")
    assert rbdb is not None, (
        f"expected derived.ranged_bow_damage_bonus, got: {data.get('derived')!r}"
    )
    assert rbdb.get("bonus") == 2, f"expected +2, got: {rbdb!r}"
    assert any(
        "Bracers of Archery" in str(s) for s in rbdb.get("sources") or []
    ), f"expected the bracers named in sources, got: {rbdb!r}"


async def test_bracers_of_archery_detune_drops_derived(gm_client, roster):
    """Attunement gate: un-attuning the bracers (still equipped) removes
    `derived.ranged_bow_damage_bonus`. Restores inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BRACERS_SLUG),
        None,
    )
    assert idx is not None, "Rowan has no Bracers of Archery item"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        assert "ranged_bow_damage_bonus" not in (data2.get("derived") or {}), (
            f"expected no ranged_bow_damage_bonus after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_bracers_of_archery_unequip_drops_derived(gm_client, roster):
    """Unequipping the bracers removes `derived.ranged_bow_damage_bonus`.
    Restores inventory on teardown."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BRACERS_SLUG),
        None,
    )
    assert idx is not None, "Rowan has no Bracers of Archery item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        assert "ranged_bow_damage_bonus" not in (data2.get("derived") or {}), (
            f"expected no ranged_bow_damage_bonus after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_bracers_of_archery_adds_longbow_damage(gm_client, roster):
    """End-to-end: Rowan's Longbow (1d8+4) carries an extra +2 flat damage
    modifier while the bracers are attuned; detuning the bracers drops the +2
    back to the base +4. Asserts on the flat-modifier sum in the damage
    breakdown (stable across random die faces and crits)."""
    rowan = roster["Rowan Quickbow"]
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BRACERS_SLUG),
        None,
    )
    assert idx is not None, "Rowan has no Bracers of Archery item"
    try:
        with_bracers = await _attack(gm_client, rowan["id"], _LONGBOW_INDEX)
        assert with_bracers["attack_name"] == "Longbow"
        mods_with = _flat_modifier_sum(with_bracers.get("damage_breakdown") or "")
        assert mods_with == 6, (
            f"expected flat mods 4(DEX)+2(bracers)=6 with bracers, got "
            f"{mods_with} (breakdown {with_bracers.get('damage_breakdown')!r})"
        )

        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        without_bracers = await _attack(gm_client, rowan["id"], _LONGBOW_INDEX)
        mods_without = _flat_modifier_sum(
            without_bracers.get("damage_breakdown") or ""
        )
        assert mods_without == 4, (
            f"expected flat mods 4(DEX) after detune, got "
            f"{mods_without} (breakdown "
            f"{without_bracers.get('damage_breakdown')!r})"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_bracers_of_archery_skips_melee_weapon(gm_client, roster):
    """Gate: the +2 is ranged-bow only — Rowan's off-hand Shortsword (melee,
    1d6, no ability mod) gets no flat bonus even with the bracers attuned."""
    rowan = roster["Rowan Quickbow"]
    data = await _attack(gm_client, rowan["id"], _SHORTSWORD_INDEX)
    assert data["attack_name"] == "Shortsword"
    mods = _flat_modifier_sum(data.get("damage_breakdown") or "")
    assert mods == 0, (
        f"expected 0 flat mods (no bracers bonus on a melee weapon), got "
        f"{mods} (breakdown {data.get('damage_breakdown')!r})"
    )
