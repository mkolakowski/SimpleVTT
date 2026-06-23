"""v2.585.0 — app-wide GM role gates campaign creation (Arc A2 of
``docs/plans/app-wide-roles-and-storage.md``).

``POST /campaigns`` now requires the GM role (``is_gm``) or admin via
``require_gm``; a GM who is not an admin is capped at
``GM_CAMPAIGN_LIMIT`` owned campaigns. Demo roster (post-A1):
``demo-gm@example.com`` is a GM, ``demo-alice``/``demo-bob`` are players.

Live tests only (need the running app + demo seed); skip when the app
isn't reachable.
"""
import httpx
import pytest

from .helpers import BASE_URL, login_client


def _app_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


@_LIVE
async def test_player_cannot_create_campaign():
    """A player (demo-alice, is_gm=False, not admin) is refused with 403 —
    the GM role gate fires; no campaign is created."""
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await client.post(
            "/campaigns",
            data={"name": "player-should-not-create", "game_system": "generic"},
        )
        assert resp.status_code == 403, resp.text[:200]
        assert "gm" in resp.text.lower()
    finally:
        await client.aclose()


@_LIVE
async def test_gm_can_create_campaign():
    """A GM (demo-gm, is_gm=True) passes the gate and creates a campaign —
    the POST 303-redirects to the new campaign page (followed to 200).
    (No GM-facing campaign delete exists; the row lingers until the demo
    reseed. CI boots fresh per run.)"""
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        resp = await client.post(
            "/campaigns",
            data={"name": "a2-gm-create-test", "game_system": "generic"},
        )
        # follow_redirects=True → we land on the new campaign view.
        assert resp.status_code == 200, resp.text[:200]
        assert "/campaign/" in str(resp.url)
    finally:
        await client.aclose()


@_LIVE
async def test_create_campaign_requires_login():
    """An unauthenticated POST is refused (401/403/303-to-login), never
    creating a campaign."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as c:
        resp = await c.post("/campaigns", data={"name": "anon", "game_system": "generic"})
    assert resp.status_code in (303, 401, 403)
    assert not (200 <= resp.status_code < 303)


# ---- A3: player character cap (v2.586.0) ----------------------------------

@_LIVE
async def test_player_character_cap_blocks_at_limit():
    """A player (demo-alice) creating standalone characters eventually hits
    the PLAYER_CHARACTER_LIMIT cap → 403 with a 'limit' message. (Standalone
    chars need no campaign membership; they're cleared on the demo reseed.)"""
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        saw_403 = False
        # Default cap is 5; alice already owns ≥1 PC, so a 403 must appear
        # within a bounded number of attempts.
        for i in range(8):
            resp = await client.post(
                "/characters/new-standalone",
                data={"name": f"a3-cap-probe-{i}", "template": "generic"},
            )
            if resp.status_code == 403:
                saw_403 = True
                assert "limit" in resp.text.lower()
                break
            assert resp.status_code == 200, resp.text[:200]
        assert saw_403, "player never hit the character cap within 8 creates"
    finally:
        await client.aclose()


@_LIVE
async def test_gm_characters_uncapped():
    """A GM (demo-gm, is_gm=True) is uncapped — several standalone creates
    all succeed (no 403), even though the GM already owns many PCs."""
    client = await login_client("demo-gm@example.com", "demopass")
    try:
        for i in range(3):
            resp = await client.post(
                "/characters/new-standalone",
                data={"name": f"a3-gm-uncapped-{i}", "template": "generic"},
            )
            assert resp.status_code == 200, f"GM create {i} refused: {resp.status_code} {resp.text[:200]}"
    finally:
        await client.aclose()
