"""Demo multi-campaign shape (v2.591.0+).

Tracks the demo-rework arc: five leveled sample campaigns (levels 3/5/9/13/18),
shared players, and a second GM (demo-gm2) who owns one campaign. This file
grows as each campaign lands (phases D3–D6); for now it locks in the expanded
user roster from phase D2. Live-only — skips when the app isn't reachable.
"""
import httpx
import pytest

from .helpers import BASE_URL, login_client

_DEMO_ACCOUNTS = [
    "demo-gm@example.com",
    "demo-alice@example.com",
    "demo-bob@example.com",
    "demo-gm2@example.com",
    "demo-carol@example.com",
    "demo-dave@example.com",
    "demo-erin@example.com",
]


def _app_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


@_LIVE
@pytest.mark.parametrize("email", _DEMO_ACCOUNTS)
async def test_demo_account_can_log_in(email):
    """Every seeded demo account (3 original + demo-gm2 + 3 new players)
    logs in with the shared demo password."""
    client = await login_client(email, "demopass")
    try:
        # The lobby renders for an authed user (200, not a bounce to /login).
        resp = await client.get("/")
        assert resp.status_code == 200, f"{email}: {resp.status_code}"
    finally:
        await client.aclose()


@_LIVE
@pytest.mark.parametrize("email", ["demo-gm@example.com", "demo-alice@example.com", "demo-carol@example.com"])
async def test_goblin_warrens_present_for_gm_and_members(email):
    """D3 — the level-3 'Goblin Warrens' campaign shows in its GM's lobby
    (demo-gm owns it) and its members' lobbies (alice + carol are members)."""
    client = await login_client(email, "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Goblin Warrens" in resp.text, f"{email} lobby missing the L3 campaign"
    finally:
        await client.aclose()


@_LIVE
@pytest.mark.parametrize("email", ["demo-gm2@example.com", "demo-bob@example.com", "demo-dave@example.com", "demo-erin@example.com"])
async def test_saltmarsh_present_for_second_gm_and_members(email):
    """D4 — the level-9 'Storm Over Saltmarsh' campaign shows in the SECOND
    GM's lobby (demo-gm2 owns it) and its members' lobbies (bob/dave/erin)."""
    client = await login_client(email, "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Saltmarsh" in resp.text, f"{email} lobby missing the L9 campaign"
    finally:
        await client.aclose()


@_LIVE
@pytest.mark.parametrize("email", ["demo-gm@example.com", "demo-bob@example.com", "demo-dave@example.com"])
async def test_shadowfell_spire_present(email):
    """D5 — the level-13 'Shadowfell Spire' campaign shows in its GM's
    (demo-gm) + members' (bob/dave) lobbies."""
    client = await login_client(email, "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Shadowfell Spire" in resp.text, f"{email} lobby missing the L13 campaign"
    finally:
        await client.aclose()


@_LIVE
@pytest.mark.parametrize("email", ["demo-gm@example.com", "demo-carol@example.com", "demo-erin@example.com"])
async def test_dragons_apotheosis_present(email):
    """D6 — the level-18 'Dragon's Apotheosis' campaign shows in its GM's
    (demo-gm) + members' (carol/erin) lobbies."""
    client = await login_client(email, "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Apotheosis" in resp.text, f"{email} lobby missing the L18 campaign"
    finally:
        await client.aclose()


@_LIVE
async def test_shared_player_sees_multiple_campaigns():
    """D7 — carol is a shared player: a member of both the level-3 Goblin
    Warrens and the level-5 Sundered Vault, so her lobby lists both."""
    client = await login_client("demo-carol@example.com", "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Goblin Warrens" in resp.text and "Sundered Vault" in resp.text
    finally:
        await client.aclose()


@_LIVE
async def test_all_five_campaigns_seeded():
    """D6 — the full arc: an admin sees all five leveled campaigns by name.
    (demo-gm is site-admin by default → the lobby's admin 'all campaigns'
    list includes every campaign; skips if the GM isn't admin on this stack.)"""
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        text = resp.text
        # demo-gm owns 4 of the 5 (all but Saltmarsh); those 4 always show.
        for name in ("Sundered Vault", "Goblin Warrens", "Shadowfell Spire", "Apotheosis"):
            assert name in text, f"lobby missing {name!r}"
    finally:
        await client.aclose()


@_LIVE
async def test_second_gm_owns_only_its_campaign():
    """demo-gm2 owns exactly the L9 campaign — its lobby shows Saltmarsh but
    not the demo-gm-owned campaigns (e.g. the Goblin Warrens)."""
    client = await login_client("demo-gm2@example.com", "demopass")
    try:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "Saltmarsh" in resp.text
        assert "Goblin Warrens" not in resp.text
    finally:
        await client.aclose()
