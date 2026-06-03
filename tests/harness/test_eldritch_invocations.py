"""v2.99.89 — Eldritch Invocations: Agonizing Blast mechanical wiring.

RAW (PHB p.110): Agonizing Blast — "When you cast Eldritch Blast,
add your Charisma modifier to the damage of each beam it deals."

Server-side ``_pc_agonizing_blast_bonus(sheet, attack)`` returns
the CHA modifier when the Warlock has the invocation on their
feats list AND the attack name contains "eldritch blast" (case-
insensitive). Appended to ``damage_expr_raw`` in /attack right
after the Two-Weapon Fighting block.

Demo fixture: Magnus Hexbinder (Warlock Lv 5, CHA 17 mod +3,
Agonizing Blast on his feats list). v2.99.89 strips the pre-baked
"+3" from his Eldritch Blast damage ("1d10+3" → "1d10") so the
auto-apply doesn't double-add. End damage is identical.

Tests:
- happy: Magnus's Eldritch Blast damage expression carries the +3.
- gate: A non-Warlock PC's "Eldritch Blast"-named attack stays
  unchanged (no invocation on feats list → no swap).
- name gate: Magnus's Quarterstaff (non-Eldritch-Blast attack)
  doesn't get the bonus.
"""
import re
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ELDRITCH_BLAST_INDEX = 1  # Magnus's attack list: [Quarterstaff, Eldritch Blast]


async def _attack(gm_client, gm_ws, char_id, attack_index):
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": char_id,
            "attack_index": attack_index,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    return msg["data"]


def _leading_addends_count(expr):
    """Count the number of '+N' literal addends (digits only) in
    the damage expression, e.g. '1d10+3' → 1; '1d10' → 0;
    '1d10+3+2' → 2.
    """
    return len(re.findall(r"\+\d+", expr or ""))


async def test_agonizing_blast_appends_cha_mod_to_eldritch_blast(
    gm_client, gm_ws, roster,
):
    """Magnus's Eldritch Blast (sheet damage "1d10") should fire with
    damage_expr ending in "+3" (Magnus's CHA mod). The auto-apply
    runs because (a) Agonizing Blast is on his feats list and
    (b) the attack name contains "eldritch blast".
    """
    magnus = roster["Magnus Hexbinder"]
    data = await _attack(gm_client, gm_ws, magnus["id"], ELDRITCH_BLAST_INDEX)
    dmg_expr = data.get("damage_expr") or ""
    assert dmg_expr.endswith("+3"), (
        f"Agonizing Blast should append Magnus's CHA mod (+3) to "
        f"Eldritch Blast damage; got {dmg_expr!r}"
    )


async def test_agonizing_blast_skipped_on_non_eldritch_blast_attack(
    gm_client, gm_ws, roster,
):
    """Magnus's Quarterstaff (index 0, not Eldritch Blast) → no
    Agonizing Blast bonus. The attack-name gate short-circuits
    on the non-EB attack name.
    """
    magnus = roster["Magnus Hexbinder"]
    # Quarterstaff is index 0 in Magnus's attacks.
    data = await _attack(gm_client, gm_ws, magnus["id"], 0)
    dmg_expr = data.get("damage_expr") or ""
    # Magnus's Quarterstaff sheet damage is "1d6+0" (Magnus is a
    # caster, doesn't fight with the staff often — STR 8 mod -1
    # → bare "1d6" baseline + nothing added). The Quarterstaff
    # damage shouldn't carry an extra "+3".
    assert "+3" not in dmg_expr, (
        f"Agonizing Blast should NOT fire on a non-Eldritch-Blast "
        f"attack; got {dmg_expr!r} with a +3 addend"
    )


async def test_agonizing_blast_skipped_for_non_warlock(
    gm_client, gm_ws, roster,
):
    """A non-Warlock PC with an "Eldritch Blast"-named attack but
    no Agonizing Blast invocation on their feats list shouldn't
    get the bonus. Krieger (Barbarian) doesn't have Eldritch Blast
    natively, so we PATCH it onto his attacks list temporarily.
    """
    krieger = roster["Krieger Stonefist"]
    # Snapshot original attacks by reading the roster (roster
    # entries don't carry the sheet but the attacks are accessible
    # through /attack with the existing indices). For this test
    # we PATCH a synthetic Eldritch Blast at index 0 and restore.
    # Krieger's seed attacks: [Greataxe, Javelin]. We prepend EB
    # so its index is 0.
    synthetic = {
        "name": "Eldritch Blast (synthetic)",
        "attack_bonus": "+7",
        "damage": "1d10",
        "damage_type": "force",
        "range": "120 ft",
    }
    # Replace attacks with [EB, Greataxe, Javelin] (we don't know
    # Krieger's existing attacks exactly without a sheet GET; use
    # a single-EB list to keep this test isolated). Restore the
    # original list (also single-EB at index 0) in finally — the
    # test's correctness depends on /attack accepting the index +
    # the attack carrying the EB name, regardless of the rest.
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": [synthetic]},
        )
        data = await _attack(gm_client, gm_ws, krieger["id"], 0)
        dmg_expr = data.get("damage_expr") or ""
        # Krieger doesn't have the invocation on his feats. The
        # damage stays at "1d10".
        assert dmg_expr == "1d10", (
            f"Non-Warlock without Agonizing Blast invocation should "
            f"NOT get the +CHA on Eldritch Blast; got {dmg_expr!r}"
        )
    finally:
        # Restore Krieger's seed attacks. The seed has Greataxe +
        # Javelin (see app/demo_seed.py); reseed via the canonical
        # values so we don't leak a synthetic EB into other tests.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
            json={"attacks": [
                {"name": "Greataxe", "attack_bonus": "+7", "damage": "1d12+4",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Two-handed, heavy."},
                {"name": "Javelin", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "30/120 ft",
                 "desc": "Thrown."},
            ]},
        )
