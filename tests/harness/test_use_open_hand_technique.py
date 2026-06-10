"""Monk Open Hand Technique — Way of the Open Hand subclass feature.

v2.49.57 — adds ``POST /api/campaign/{cid}/use_open_hand_technique``.
Monk Way of the Open Hand Lv 3+. RAW: when monk hits with a Flurry
of Blows attack, they may impose one of three riders on the target
(see endpoint docstring). Modeled on Stunning Strike — same trust-
the-caller convention for the "must follow a Flurry hit" gate (UI is
expected to surface the button only after a Flurry hit).

Three modes:
  - ``prone``: DEX save vs DC 8 + monk prof + WIS mod. On fail
    install Prone. Routes through the save-or-suck pipeline + the
    new ``open-hand-prone`` entry in ``_SPELL_CONDITION_MAP``.
  - ``push``: STR save vs the same DC. No buff installed; response
    carries ``push_authorized`` so the GM UI can drag the token.
  - ``no_reactions``: no save, install ``reaction-denied`` buff
    inline (1-turn duration, RAW).

Tests:
  - prone NPC happy path: Kael uses prone on a bandit; retry until
    save fails; assert Prone installed + 200 response shape.
  - push NPC happy path: Kael uses push on a bandit; assert response
    carries ``push_authorized`` matching the (server-rolled) save
    outcome (False on pass, True on fail). Single-iteration assert
    (push_authorized is non-None either way).
  - no_reactions NPC: no save, immediate install; assert
    ``reaction-denied`` lands + roll-log entry fires.
  - 409 wrong_class: Krieger (Barbarian) → 409 wrong_class.
  - 409 wrong_subclass: Garrik (Fighter? no — pick a monk from a
    different subclass if any, else fall back to the wrong_class
    test). Demo only has one monk and it's Open Hand, so this case
    is covered with a sheet-patch trick: temporarily change Kael's
    subclass via /sheet PATCH, fire the endpoint, restore.
  - 400 bad mode: invalid mode string → 400.
"""
import asyncio
import time

import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


async def test_open_hand_prone_happy_path_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Open Hand (prone) on a bandit; retry until DEX save
    fails; assert Prone buff installed (key='prone', concentration=False)."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_prone"

    saw_prone = False
    for _ in range(20):
        await _seed_battle(gm_client, [
            {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 38, "hp_max": 38, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 11, "hp_max": 11, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
                "mode": "prone",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["mode"] == "prone"
        assert body["auto_save_target_kind"] == "npc"
        assert body["save_dc"] > 0
        assert body["auto_save_rolled"] is not None
        assert body["auto_save_passed"] is not None
        if body["auto_save_passed"]:
            continue
        assert body["auto_save_buff_installed"] == "Prone"
        bu = await gm_ws.wait_for("battle_update", timeout=2.0)
        combatants = (bu.get("data") or {}).get("combatants") or []
        bandit = next(
            (c for c in combatants if c.get("id") == bandit_id), None,
        )
        assert bandit is not None
        prone_buffs = [
            b for b in (bandit.get("buffs") or [])
            if (b or {}).get("key") == "prone"
        ]
        assert prone_buffs, f"Prone missing; got {bandit.get('buffs')}"
        assert prone_buffs[0].get("concentration") is False
        assert prone_buffs[0].get("source_char_id") == kael["id"]
        saw_prone = True
        break

    assert saw_prone, "no save failure in 20 attempts — flaky env?"


async def test_open_hand_push_npc(gm_client, kael_rested):
    """Kael uses Open Hand (push) on a bandit. NPC path: server rolls
    inline; response carries ``push_authorized`` matching the save
    outcome. No buff installed either way (push has no
    _SPELL_CONDITION_MAP entry).
    """
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_push"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "push",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "push"
    assert body["auto_save_target_kind"] == "npc"
    assert body["auto_save_rolled"] is not None
    assert body["auto_save_passed"] is not None
    assert body["push_authorized"] is not None
    # push_authorized is the boolean inverse of the save outcome.
    assert body["push_authorized"] == (not body["auto_save_passed"])
    # No buff installed in push mode.
    assert body["auto_save_buff_installed"] == ""


async def _token_y_by_id(gm_client, token_id):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in resp.json()["tokens"]:
        if t["id"] == token_id:
            return float(t["y"])
    return None


async def test_open_hand_push_moves_target_on_failed_save(
    gm_client, kael_rested,
):
    """v2.99.434 — Phase 6.3: on a failed STR save, Open Hand push moves
    the bandit's token 15 ft away from Kael via _force_move.

    Kael's token is placed directly above the bandit (same x) so the push
    is straight down (+y). The save is server-rolled, so loop until the
    bandit fails — then ``push_applied`` is True and the bandit's token
    moved +210 px (3 cells / 15 ft on the 70-px grid). On a pass nothing
    moves. The NPC token is created here + torn down at the end.
    """
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)

    # Real NPC token for the bandit so _force_move can resolve + mutate it.
    rt = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"token_template_id": bandit_tmpl["id"], "x": 700.0, "y": 700.0},
    )
    assert rt.status_code == 200, rt.text
    bandit_tok_id = rt.json()["id"]

    # Kael's token directly above the bandit → push direction is +y (down).
    rp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/place-token",
        json={"x": 700.0, "y": 560.0},
    )
    assert rp.status_code == 200, rp.text

    bandit_cb = "tok_test_oht_pushmove"
    try:
        pushed = False
        for _ in range(30):
            # Re-seed each iteration: the bandit combatant links to the real
            # token via source_token_id so _force_move resolves it.
            await _seed_battle(gm_client, [
                {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
                 "name": kael["name"], "initiative": 10,
                 "hp_current": 38, "hp_max": 38, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": bandit_cb, "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "source_token_id": bandit_tok_id,
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 11, "hp_max": 11, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ])
            before_y = await _token_y_by_id(gm_client, bandit_tok_id)
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
                json={
                    "character_id": kael["id"],
                    "target_combatant_id": bandit_cb,
                    "mode": "push",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["mode"] == "push"
            assert body["auto_save_target_kind"] == "npc"
            if body["auto_save_passed"] is False:
                assert body["push_authorized"] is True
                assert body["push_applied"] is True
                after_y = await _token_y_by_id(gm_client, bandit_tok_id)
                assert after_y == before_y + 210.0  # 15 ft / 3 cells
                pushed = True
                break
            # On a pass: no push, token unmoved.
            assert body["push_applied"] is False
            assert await _token_y_by_id(gm_client, bandit_tok_id) == before_y
        assert pushed, "no failed STR save in 30 attempts — flaky env?"
    finally:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/tokens/{bandit_tok_id}"
        )


async def test_open_hand_no_reactions_npc(gm_client, gm_ws, kael_rested):
    """Kael uses Open Hand (no_reactions) on a bandit. No save —
    immediate install of ``reaction-denied`` buff + public roll-log
    entry."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_noreact"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "no_reactions",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "no_reactions"
    assert body["auto_save_prompted"] is False
    assert body["buff_installed"] == "No Reactions (Open Hand)"
    bu = await gm_ws.wait_for("battle_update", timeout=2.0)
    combatants = (bu.get("data") or {}).get("combatants") or []
    bandit = next(
        (c for c in combatants if c.get("id") == bandit_id), None,
    )
    assert bandit is not None
    buffs = [
        b for b in (bandit.get("buffs") or [])
        if (b or {}).get("key") == "reaction-denied"
    ]
    assert buffs, f"reaction-denied missing; got {bandit.get('buffs')}"
    assert buffs[0].get("concentration") is False
    assert buffs[0].get("duration_rounds") == 1
    assert buffs[0].get("source_char_id") == kael["id"]


async def test_open_hand_wrong_class(gm_client, roster):
    """Krieger (Barbarian) → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_wrong"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{krieger['id']}", "char_id": krieger["id"],
         "name": krieger["name"], "initiative": 10,
         "hp_current": 55, "hp_max": 55, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": bandit_id,
            "mode": "prone",
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "monk"


async def test_open_hand_bad_mode(gm_client, kael_rested):
    """Invalid mode string → 400."""
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_oht_badmode"
    await _seed_battle(gm_client, [
        {"id": f"tok_test_{kael['id']}", "char_id": kael["id"],
         "name": kael["name"], "initiative": 10,
         "hp_current": 38, "hp_max": 38, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": bandit_id, "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7,
         "hp_current": 11, "hp_max": 11, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": bandit_id,
            "mode": "spinning_palm_of_doom",
        },
    )
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# PC integration tests — closes the v2.49.57 filed item.
#
# Three modes, all PC-target paths:
#   - prone: roll_request → /respond installs Prone via
#     `_SPELL_CONDITION_MAP["open-hand-prone"]`. Prone is NOT in
#     `_INCAPACITATING_BUFF_KEYS` (Prone constrains movement but doesn't
#     incapacitate), so the v2.49.51 hook does NOT fire — the target's
#     own concentration anchors must survive. This is the load-bearing
#     regression guard for the "non-incapacitating condition buff"
#     branch of the hook.
#   - push: roll_request → /respond is a no-op for the install (no
#     `_SPELL_CONDITION_MAP` entry for `open-hand-push`). The save
#     total appears in the roll log; the GM observes + drags the
#     token. Asserts that auto_buff_installed is empty.
#   - no_reactions: no save, inline install via `_install_buff` (PC
#     path). Verify reaction-denied lands on the PC's hub + sheet
#     mirror.
# ---------------------------------------------------------------------------

async def _install_hex(gm_client, magnus_id: int, target_id: int):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus_id,
            "target_character_id": target_id,
            "ability": "STR",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text


async def _buff_keys(gm_client, char_id: int) -> list[str]:
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )
    if r.status_code != 200:
        return []
    return [(b or {}).get("key") for b in r.json().get("buffs", [])]


def _pc_combatant(char, tid_prefix: str, hp: int = 30, init: int = 10):
    return {
        "id": f"{tid_prefix}_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_open_hand_prone_pc_installs_prone(gm_client, kael_rested, roster):
    """Kael uses Open Hand (prone) on Magnus → roll_request flow. GM
    responds for Magnus; retry until DEX save fails; assert Prone
    lands. Magnus's pre-existing Hex MUST survive (Prone is not in
    _INCAPACITATING_BUFF_KEYS, so the v2.49.51 hook is a no-op)."""
    kael = kael_rested
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]

    saw_prone = False
    for _ in range(20):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
            json={"type": "long"},
        )
        for k in ("prone", "hex"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": magnus["id"], "key": k},
            )
        await _seed_battle(gm_client, [
            _pc_combatant(kael, "tok_oht_k", hp=38),
            _pc_combatant(magnus, "tok_oht_m", hp=30),
            _pc_combatant(pip, "tok_oht_p"),
        ])
        # Magnus casts Hex on Pip (now concentrating).
        await _install_hex(gm_client, magnus["id"], pip["id"])
        pre_keys = await _buff_keys(gm_client, magnus["id"])
        assert "hex" in pre_keys, f"pre-cond: hex should land; got {pre_keys}"

        cast_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
            json={
                "character_id": kael["id"],
                "target_combatant_id": f"tok_oht_m_{magnus['id']}",
                "mode": "prone",
            },
        )
        assert cast_resp.status_code == 200, cast_resp.text
        body = cast_resp.json()
        assert body["mode"] == "prone"
        assert body["auto_save_target_kind"] == "pc"
        assert body["auto_save_prompted"] is True
        prompt_id = body["auto_save_prompt_id"]
        assert isinstance(prompt_id, int) and prompt_id > 0

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": magnus["id"]},
        )
        assert r.status_code == 200, r.text
        if r.json().get("auto_buff_installed") != "Prone":
            continue  # save passed; retry

        # Prone lands on Magnus.
        post_keys = await _buff_keys(gm_client, magnus["id"])
        assert "prone" in post_keys, (
            f"Prone should land on Magnus; got {post_keys}"
        )
        # Hex MUST survive — Prone isn't in _INCAPACITATING_BUFF_KEYS,
        # so the v2.49.51 hook doesn't fire on this install. Regression
        # guard for the "non-incapacitating buff" branch.
        assert "hex" in post_keys, (
            f"Magnus's Hex should survive a Prone install (Prone is "
            f"not incapacitating, v2.49.51 hook must be a no-op here); "
            f"got {post_keys}"
        )
        saw_prone = True
        break

    assert saw_prone, "no DEX save failure in 20 attempts — flaky env?"

    # Cleanup.
    for k in ("prone", "hex"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )


async def test_open_hand_push_pc_no_buff(gm_client, kael_rested, roster):
    """Kael uses Open Hand (push) on Magnus → roll_request. The save
    completes via /respond but no buff installs (push has no
    _SPELL_CONDITION_MAP entry — the GM observes the save result in
    the roll log and acts manually). Response shape: auto_save_prompted=
    True, auto_buff_installed empty."""
    kael = kael_rested
    magnus = roster["Magnus Hexbinder"]

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    for k in ("prone", "hex"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    await _seed_battle(gm_client, [
        _pc_combatant(kael, "tok_oht_k", hp=38),
        _pc_combatant(magnus, "tok_oht_m", hp=30),
    ])

    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": f"tok_oht_m_{magnus['id']}",
            "mode": "push",
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text
    body = cast_resp.json()
    assert body["mode"] == "push"
    assert body["auto_save_target_kind"] == "pc"
    assert body["auto_save_prompted"] is True
    # push has no map entry → cast response carries no buff name.
    assert body["auto_save_buff_installed"] == ""
    prompt_id = body["auto_save_prompt_id"]
    assert isinstance(prompt_id, int) and prompt_id > 0

    # Even on a failed save, /respond must NOT install anything for
    # push mode (the spell_slug "open-hand-push" has no
    # _SPELL_CONDITION_MAP entry, so the /respond install branch is
    # a no-op).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("auto_buff_installed", "") == "", (
        f"push should never install a buff; got {r.json()}"
    )
    # No prone / no reaction-denied / no anything-new on Magnus.
    post_keys = await _buff_keys(gm_client, magnus["id"])
    assert "prone" not in post_keys
    assert "reaction-denied" not in post_keys


async def test_open_hand_no_reactions_pc(gm_client, gm_ws, kael_rested, roster):
    """Kael uses Open Hand (no_reactions) on Magnus → no save, inline
    install of reaction-denied via _install_buff. Verify the buff
    lands on Magnus's hub state + sheet mirror + a public roll-log
    entry naming Kael and Magnus."""
    kael = kael_rested
    magnus = roster["Magnus Hexbinder"]

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    for k in ("reaction-denied", "hex"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )
    await _seed_battle(gm_client, [
        _pc_combatant(kael, "tok_oht_k", hp=38),
        _pc_combatant(magnus, "tok_oht_m", hp=30),
    ])
    gm_ws.mark()

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_open_hand_technique",
        json={
            "character_id": kael["id"],
            "target_combatant_id": f"tok_oht_m_{magnus['id']}",
            "mode": "no_reactions",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "no_reactions"
    assert body["auto_save_target_kind"] == "pc"
    assert body["auto_save_prompted"] is False
    assert body["buff_installed"] == "No Reactions (Open Hand)"

    # Hub + sheet mirror.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        keys = await _buff_keys(gm_client, magnus["id"])
        if "reaction-denied" in keys:
            break
        await asyncio.sleep(0.05)
    b = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )
    resp = b.json()
    hub_keys = [(bf or {}).get("key") for bf in resp.get("buffs", [])]
    sheet_keys = [(bf or {}).get("key") for bf in resp.get("sheet_buffs", [])]
    assert "reaction-denied" in hub_keys, (
        f"reaction-denied missing from hub; got {hub_keys}"
    )
    assert "reaction-denied" in sheet_keys, (
        f"reaction-denied missing from sheet mirror; got {sheet_keys}"
    )
    # Buff shape.
    rd = next(b for b in resp["buffs"] if (b or {}).get("key") == "reaction-denied")
    assert rd.get("source_char_id") == kael["id"]
    assert rd.get("duration_rounds") == 1
    assert rd.get("concentration") is False

    # 🫷 public roll-log entry.
    no_react_logs = [
        m for m in gm_ws.buffered("roll")
        if "🫷" in ((m.get("data") or {}).get("note") or "")
        and kael["name"] in ((m.get("data") or {}).get("note") or "")
        and magnus["name"] in ((m.get("data") or {}).get("note") or "")
    ]
    assert no_react_logs, (
        f"expected 🫷 log naming both; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )

    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "reaction-denied"},
    )
