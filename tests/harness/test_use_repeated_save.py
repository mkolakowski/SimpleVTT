"""v2.97.60 — end-of-turn repeated-save endpoint + PFE&G save advantage.

Three tests:

1. ``test_repeated_save_picks_up_pfeag_advantage`` — Lyra (test
   ``creature_type: "fiend"`` override) casts Fear on Pip; loop until
   Pip fails. Caelan wards Pip with PFE&G (covers fiend). Pip POSTs
   /use_repeated_save with buff_key="frightened". The response carries
   ``pfeag_advantage_applied: True``.

2. ``test_repeated_save_without_pfeag_runs_straight`` — Same Fear
   install (Lyra still flagged fiend), but NO PFE&G ward on Pip. Pip
   POSTs /use_repeated_save. Response carries
   ``pfeag_advantage_applied: False``.

3. ``test_repeated_save_without_buff_returns_409`` — Pip has no
   matching buff → 409 ``no_buff``.

Notes:
- The v2.97.60 install-time stamp lives in /respond's save-or-suck
  condition-install path. The test casts Fear and walks the save-fail
  loop just like ``test_pfeag_condition_immunity``, leaning on the
  v2.97.48 ``creature_type`` runtime override on Lyra's combatant.
- Pip's Wis save mod is low so the 30-iteration loop reliably lands
  a fail.
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _install_frightened_from_lyra(
    gm_client, lyra, pip, caelan=None, pfeag_on_pip=False,
):
    """Helper: seed battle (with optional Caelan), have Lyra (creature_type="fiend")
    cast Fear on Pip, loop until Pip fails the Wis save and Frightened lands.
    Optionally has Caelan cast PFE&G on Pip BEFORE the Fear cast so the
    v2.97.49 immunity gate does NOT trigger (PFE&G ward is on Pip, but the
    immunity gate is what we want to test repeated saves against — so we
    DON'T install PFE&G here, we install it AFTER the Fear lands).

    Returns the cast_id + the chosen tokens dict so the caller can install
    PFE&G afterwards (post-Frightened install) and then call /use_repeated_save.
    """
    lyra_tok = f"tok_rs_lyra_{lyra['id']}"
    pip_tok = f"tok_rs_pip_{pip['id']}"
    caelan_tok = f"tok_rs_caelan_{caelan['id']}" if caelan else None

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        if caelan:
            await _long_rest(gm_client, caelan["id"])
        # aggressive cleanup
        for _stale in (
            "frightened", "paralyzed", "charmed", "baned", "faerie-fired",
            "protection-from-evil-and-good", "heroism", "bless",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale},
            )

        combatants = []
        if caelan:
            combatants.append({
                "id": caelan_tok, "char_id": caelan["id"],
                "name": caelan["name"], "initiative": 16,
                "hp_current": 60, "hp_max": 60, "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            })
        combatants.append({
            "id": lyra_tok, "char_id": lyra["id"],
            "name": lyra["name"], "initiative": 12,
            "hp_current": 35, "hp_max": 35, "buffs": [],
            "creature_type": "fiend",
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
        combatants.append({
            "id": pip_tok, "char_id": pip["id"],
            "name": pip["name"], "initiative": 8,
            "hp_current": 40, "hp_max": 40, "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": combatants,
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        # Cast Fear on Pip (Lyra's Fear index 19 per v2.97.43).
        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,
                "slot_level": 3,
                "class_slug": "bard",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        prompt_id = fear_cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        # Pip responds to the save.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        data = resp.json()
        if data.get("auto_buff_installed") == "Frightened":
            landed = True
            break

    assert landed, "no failed Wis save in 30 tries; couldn't install Frightened"
    return {
        "lyra_tok": lyra_tok,
        "pip_tok": pip_tok,
        "caelan_tok": caelan_tok,
    }


async def test_repeated_save_picks_up_pfeag_advantage(
    gm_client, roster,
):
    """Lyra (fiend test override) Fears Pip; Caelan THEN wards Pip with
    PFE&G; Pip calls /use_repeated_save; response carries
    ``pfeag_advantage_applied: True``."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    caelan = roster["Sir Caelan Lightbringer"]

    toks = await _install_frightened_from_lyra(
        gm_client, lyra, pip, caelan,
    )

    # Now Caelan casts PFE&G on Pip (spell_index 3, L1). Pip has
    # Frightened from Lyra; PFE&G goes on top with fiend in protected list.
    pfeag_cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": 3,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_character_id": pip["id"],
            "target_combatant_id": toks["pip_tok"],
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert pfeag_cast.status_code == 200, pfeag_cast.text

    # Confirm Pip carries BOTH Frightened (with stamp) AND PFE&G.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    frightened = next(
        (b for b in pip_buffs if (b or {}).get("key") == "frightened"), None,
    )
    assert frightened is not None
    assert (frightened.get("repeated_save_ability") or "").upper() == "WIS"
    assert int(frightened.get("repeated_save_dc") or 0) > 0
    assert (frightened.get("source_caster_creature_type") or "").lower() == "fiend"
    assert any(
        (b or {}).get("key") == "protection-from-evil-and-good"
        for b in pip_buffs
    )

    # Pip rolls the repeated save.
    rs = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": pip["id"], "buff_key": "frightened"},
    )
    assert rs.status_code == 200, rs.text
    data = rs.json()
    assert data["ok"] is True
    assert data["save_ability"] == "WIS"
    assert data["save_dc"] > 0
    assert data["pfeag_advantage_applied"] is True
    # The broadcast expression should contain "2d20kh1" (advantage shape).
    # We can't read the WS event from this assertion directly (no gm_ws
    # in this test) — but the rolled total being deterministic is enough.
    assert isinstance(data["total"], int)
    assert isinstance(data["passed"], bool)


async def test_repeated_save_without_pfeag_runs_straight(
    gm_client, roster,
):
    """Same Fear install, no PFE&G ward → ``pfeag_advantage_applied: False``."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]

    await _install_frightened_from_lyra(gm_client, lyra, pip)

    # Pip rolls the repeated save without any PFE&G.
    rs = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": pip["id"], "buff_key": "frightened"},
    )
    assert rs.status_code == 200, rs.text
    data = rs.json()
    assert data["pfeag_advantage_applied"] is False


async def test_repeated_save_without_buff_returns_409(gm_client, roster):
    """No buff with the requested key → 409 ``no_buff``."""
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, pip["id"])
    # Make sure no frightened buff.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "frightened"},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": pip["id"], "buff_key": "frightened"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "no_buff"
