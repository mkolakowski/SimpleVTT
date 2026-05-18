"""/api/campaign/{cid}/character/{cid}/rest — short / long rest tests.

v2.15.3: Phase B.5 — Song of Rest plumbed into the short-rest
endpoint. The endpoint existed pre-2.0.0 (HD spend + recovery +
resource refill); this commit adds the Bard's passive +1dN bonus
per HD spent.

Coverage:
  - short rest happy path: Pip takes a short rest with Lyra (Lv 6
    Lore Bard) in the campaign. Response carries song_of_rest with
    die=6 + bard="Lyra Sunstrider"; the expression contains +1d6;
    the breakdown shows both dice rolled.
  - short rest no-HD edge case: depletes Pip's HD via repeated rests
    then asserts the next call returns 409 ``no_hit_dice``.
  - invalid type returns 400.

Tests use the GM client so the per-character ownership check passes
without juggling player credentials. The endpoint is read-mostly
write-safe — short rest mutates HP + HD + resources but those state
changes don't bleed into other tests that target Pip (everyone uses
override:true patterns).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_full_hd(gm_client, roster):
    """Ensure Pip has at least 1 HD available + heals him to max so
    subsequent short-rest calls have something to recover. Long rest
    refills HP + HD; we lean on the existing /rest type=long path
    rather than poking the sheet directly.
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text
    return pip


async def test_short_rest_song_of_rest_happy_path(gm_client, pip_full_hd):
    """Pip takes a short rest with Lyra (Lv 6 Lore Bard) in the demo
    party. Asserts the v2.15.3 ``song_of_rest`` field on the response
    + the expression carries the +1d6 bonus term.
    """
    pip = pip_full_hd
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "short"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["type"] == "short"
    assert data["hit_dice"]["current"] >= 0

    # Song of Rest contract: die=6 for Lyra (Lv 6 < 9 → d6 tier),
    # bard name matches the demo PC, bard_level = 6.
    sor = data["song_of_rest"]
    assert sor is not None, (
        "Song of Rest should fire — Lyra Sunstrider is Lv 6 Lore Bard "
        "and lives in the demo campaign roster."
    )
    assert sor["die"] == 6
    assert sor["bard"] == "Lyra Sunstrider"
    assert sor["bard_level"] == 6

    # Expression carries the +1d6 term. Pip is a Rogue (d8 HD) with
    # CON 13 (+1) so the expected shape is "1d8+1d6+1".
    assert "+1d6" in data["expression"], data["expression"]
    assert data["expression"].startswith("1d8")  # Rogue d8 HD

    # Breakdown shows both individual rolls, e.g. "1d8[5]+1d6[3]+1 => 9"
    assert "1d8[" in data["breakdown"], data["breakdown"]
    assert "1d6[" in data["breakdown"], data["breakdown"]


async def test_long_rest_happy_path(gm_client, roster):
    """v2.15.4: Long rest restores HP to max, clears temp HP, refills
    HD by max(1, hd_max//2), resets every spell slot's ``used`` to 0,
    and refills short+long resources. Asserts the response shape that
    the new v2.15.4 sheet handler reads from.
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["type"] == "long"
    # HP at max (Pip is Lv 5 Rogue → 38 max; the exact number is in
    # the response; just verify current == max).
    assert data["hp"]["current"] == data["hp"]["max"]
    assert data["hp"]["temp"] == 0
    # HD restored at least partway (RAW: max(1, max//2) per long rest).
    assert data["hit_dice"]["current"] >= 1
    assert data["hit_dice"]["current"] <= data["hit_dice"]["max"]
    # Resources list present (may be empty for Pip — Rogue has no
    # short/long-rest counters in the demo seed).
    assert "resources" in data


async def test_short_rest_invalid_type(gm_client, roster):
    """Type other than 'short' or 'long' returns 400."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "nap"},
    )
    assert resp.status_code == 400


async def test_short_rest_no_hit_dice(gm_client, pip_full_hd):
    """Depleting all HD then taking another short rest returns 409
    ``no_hit_dice``. Sanity check that Song of Rest doesn't change the
    no-HD branch — that's the pre-existing contract surface and would
    be the first thing to silently regress if the new code accidentally
    skipped the early-exit guard.

    Drain-loop pattern: long rest restores HD by ``max(1, hd_max/2)``
    only (RAW long-rest behavior — half max HD back per rest, not all),
    so the fixture can't guarantee Pip starts at 5/5. We short-rest
    until we hit the 409 — that IS the assertion. A safety bound stops
    a runaway loop if the guard regresses and 409 never fires.
    """
    pip = pip_full_hd
    max_attempts = 10  # Pip's max HD = 5 + fixture's long-rest +2 = safe bound
    for _ in range(max_attempts):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
            json={"type": "short"},
        )
        if resp.status_code == 409:
            body = resp.json()
            assert body.get("error") == "no_hit_dice"
            assert body.get("hit_dice", {}).get("current") == 0
            return
        assert resp.status_code == 200, resp.text
    raise AssertionError(
        f"Expected 409 no_hit_dice within {max_attempts} short rests but "
        "the endpoint kept returning 200 — the no-HD guard may have regressed."
    )
