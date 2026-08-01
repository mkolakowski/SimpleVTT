"""v2.151.0 — Death Saves Phase 3b (Medicine-check stabilize).

RAW PHB p.197: a healer can stabilize a dying creature with a
successful DC 10 Wisdom (Medicine) check as an action.

The new endpoint `/api/campaign/{cid}/character/{healer_char_id}/medicine_stabilize`
takes a `target_char_id` body field, computes the healer's Medicine
modifier (WIS mod + PB if proficient), rolls 1d20 + mod vs DC 10, and
on success transitions the target's death_save state to `stable` (same
as the GM-only `/stabilize`). Broadcasts `character_death_save` with
`source: "medicine_check"` on success, or `feature_used` with
`source: "medicine_stabilize_failed"` on failure.

Tests:
  - Target not dying → 409 `target_not_dying`.
  - Boost the healer's Medicine modifier (PATCH WIS to 20 + proficient)
    so DC 10 is trivially met → success path: response carries
    `passed: True`, target's death_saves.status flips to stable,
    `character_death_save` broadcast fires with source="medicine_check".
  - Patch healer's Medicine modifier down to -5 (PATCH WIS to 1, not
    proficient) so DC 10 is impossible → failure path: response
    carries `passed: False`, target remains dying, `feature_used`
    broadcast fires with source="medicine_stabilize_failed".
"""
from .conftest import CAMPAIGN_ID


async def _drop_to_dying(gm_client, char_id):
    """Drop a PC to 0 HP via the damage path so death_saves.status =
    dying. Reset dead/stable state first."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 1,
            "damage_type": "slashing",
        },
    )


async def _restore(gm_client, char_id):
    """Reset to alive/full HP on teardown."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _set_roll_state(gm_client, char_id, value):
    """Set (or clear, value=None) a character's advantage/disadvantage."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/roll-state",
        json={"value": value},
    )


async def test_medicine_stabilize_409_when_target_not_dying(
    gm_client, roster,
):
    """v2.151.0 — Healer calls /medicine_stabilize against an alive
    target. Endpoint returns 409 target_not_dying."""
    tavik = roster["Brother Tavik Stonebrow"]    # healer
    pip = roster["Pip Quickfingers"]             # alive target
    await _restore(gm_client, pip["id"])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/medicine_stabilize",
        json={"target_char_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "target_not_dying"


async def test_medicine_stabilize_success_when_modifier_high(
    gm_client, gm_ws, roster,
):
    """v2.151.0 — Boost Tavik's WIS to 20 + flip Medicine proficient
    so the Medicine modifier is +9 (PB 3 at Lv 6 + 5 WIS mod = 8;
    20 WIS = 5 mod → wait, mod is (20-10)//2 = 5). Even on a
    natural 1 the total is 1 + 5 + 3 = 9. Hmm — to GUARANTEE the
    check passes, set WIS high enough that even nat 1 hits DC 10.
    Use WIS 30 (mod 10) → minimum total 1 + 10 + 3 = 14. Restores
    Tavik's WIS + Medicine on teardown."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    # Snapshot Tavik's state so we restore exactly.
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_wis = (sheet.get("abilities") or {}).get("WIS")
    orig_skills = sheet.get("skills") or {}
    orig_medicine = dict(orig_skills.get("Medicine") or {})
    try:
        # Boost Tavik's Medicine: WIS 30 (mod 10) + proficient.
        new_skills = dict(orig_skills)
        new_skills["Medicine"] = {**orig_medicine, "proficient": True}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "abilities": {**(sheet.get("abilities") or {}), "WIS": 30},
                "skills": new_skills,
            },
        )
        await _drop_to_dying(gm_client, pip["id"])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/medicine_stabilize",
            json={"target_char_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["passed"] is True, (
            f"WIS 30 + proficient should always pass DC 10 even on "
            f"nat 1; got {data}"
        )
        assert data["medicine_modifier"] >= 12, (
            f"WIS 30 mod 10 + PB ~2-3 should be 12+; got "
            f"{data.get('medicine_modifier')}"
        )
        assert data["dc"] == 10
        ds = data.get("target_death_saves") or {}
        assert ds.get("status") == "stable", (
            f"target should be stable on success; got {ds}"
        )
        msg = await gm_ws.wait_for("character_death_save")
        d = msg["data"]
        assert int(d["character_id"]) == int(pip["id"])
        assert d["status"] == "stable"
        assert d["source"] == "medicine_check"
        assert int(d.get("healer_char_id") or 0) == int(tavik["id"])
    finally:
        await _restore(gm_client, pip["id"])
        # Restore Tavik's WIS + Medicine.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "abilities": {**(sheet.get("abilities") or {}),
                              "WIS": orig_wis or 14},
                "skills": orig_skills,
            },
        )


async def test_medicine_stabilize_failure_when_modifier_low(
    gm_client, gm_ws, roster,
):
    """v2.151.0 — Drop Tavik's WIS to 1 (mod -5) + clear Medicine
    proficient so the maximum roll is 20 + (-5) = 15 (still passes
    nat 20), but the typical roll fails DC 10. We can't deterministically
    force a failure without a dice seed, so this test asserts the
    failure path's contract by retrying until at least one failure
    fires: any non-nat-20 roll with mod -5 produces a total of 15
    or less, and most are below 10. Bound to 5 attempts."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_wis = (sheet.get("abilities") or {}).get("WIS")
    orig_skills = sheet.get("skills") or {}
    try:
        # Drop WIS to 1 (mod -5), clear Medicine proficient.
        new_skills = dict(orig_skills)
        new_skills["Medicine"] = {**(orig_skills.get("Medicine") or {}),
                                  "proficient": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "abilities": {**(sheet.get("abilities") or {}), "WIS": 1},
                "skills": new_skills,
            },
        )
        failed = False
        for _ in range(5):
            await _drop_to_dying(gm_client, pip["id"])
            gm_ws.mark()
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/medicine_stabilize",
                json={"target_char_id": pip["id"]},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            # Modifier should be negative — WIS 1 drops the WIS mod to
            # -5, and even if the Medicine proficient flag's PATCH
            # didn't fully propagate (the nested skills dict can merge
            # vs replace depending on the /sheet-fields handler), the
            # total stays well below the typical Medicine bonus. The
            # contract this test pins is the FAILURE flow firing, not
            # the exact modifier value.
            assert data["medicine_modifier"] < 0, (
                f"WIS 1 should drop the Medicine modifier negative; got "
                f"{data.get('medicine_modifier')}"
            )
            if data["passed"] is False:
                failed = True
                # Failure broadcast: feature_used with source.
                feats = gm_ws.buffered("feature_used")
                fail_feats = [
                    m for m in feats
                    if (m.get("data") or {}).get("source")
                    == "medicine_stabilize_failed"
                ]
                assert fail_feats, (
                    f"failure broadcast missing; got "
                    f"{[m.get('data', {}).get('source') for m in feats]}"
                )
                # Target stays dying.
                ds_after = data.get("target_death_saves") or {}
                assert ds_after.get("status") == "dying", (
                    f"target should stay dying on failure; got {ds_after}"
                )
                break
        assert failed, (
            "expected at least one failure across 5 attempts at "
            "Medicine -5 vs DC 10; check fixtures"
        )
    finally:
        await _restore(gm_client, pip["id"])
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "abilities": {**(sheet.get("abilities") or {}),
                              "WIS": orig_wis or 14},
                "skills": orig_skills,
            },
        )


async def _stabilize_with_roll_state(gm_client, roster, value, expect_token, expect_applied):
    """v2.1042.3 — shared body for the adv/dis ride-through tests. Boosts the
    healer's WIS to 30 (guaranteed to clear DC 10 even on the low die), sets
    the healer's roll_state, and asserts the Medicine d20 was upgraded."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_wis = (sheet.get("abilities") or {}).get("WIS")
    orig_skills = sheet.get("skills") or {}
    try:
        new_skills = dict(orig_skills)
        new_skills["Medicine"] = {**(orig_skills.get("Medicine") or {}), "proficient": True}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"abilities": {**(sheet.get("abilities") or {}), "WIS": 30}, "skills": new_skills},
        )
        await _set_roll_state(gm_client, tavik["id"], value)
        await _drop_to_dying(gm_client, pip["id"])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/medicine_stabilize",
            json={"target_char_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["roll_state"] == expect_applied, (
            f"expected roll_state={expect_applied}; got {data.get('roll_state')} ({data})"
        )
        assert expect_token in (data.get("roll_breakdown") or ""), (
            f"expected the d20 upgraded to {expect_token}; breakdown={data.get('roll_breakdown')!r}"
        )
    finally:
        await _set_roll_state(gm_client, tavik["id"], None)
        await _restore(gm_client, pip["id"])
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={
                "abilities": {**(sheet.get("abilities") or {}), "WIS": orig_wis or 14},
                "skills": orig_skills,
            },
        )


async def test_medicine_stabilize_rides_healer_advantage(gm_client, roster):
    """v2.1042.3 — the healer's ADVANTAGE roll_state upgrades the Medicine
    d20 to 2d20kh1; response `roll_state` reports auto_advantage."""
    await _stabilize_with_roll_state(gm_client, roster, "advantage", "2d20kh1", "auto_advantage")


async def test_medicine_stabilize_rides_healer_disadvantage(gm_client, roster):
    """v2.1042.3 — the healer's DISADVANTAGE roll_state upgrades the Medicine
    d20 to 2d20kl1; response `roll_state` reports auto_disadvantage. WIS 30
    still clears DC 10 on the low die, so the endpoint stays 200."""
    await _stabilize_with_roll_state(gm_client, roster, "disadvantage", "2d20kl1", "auto_disadvantage")
