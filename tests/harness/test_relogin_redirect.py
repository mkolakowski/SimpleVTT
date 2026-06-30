"""v2.785.0 — after a session expires, re-login returns you to where you were.

An unauthenticated HTML request to a protected page bounces to
``/login?next=<path>`` AND stashes the destination in the session, so login
methods that don't round-trip the form ``next`` (demo magic-link, Google SSO)
can still land back on the original URL.
"""
import httpx

from .helpers import BASE_URL

EDITOR = "/campaign/1/map/1/edit"


async def test_bounce_redirects_with_next():
    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=False) as c:
        r = await c.get(EDITOR, headers={"Accept": "text/html"})
        assert r.status_code == 303, r.text
        assert r.headers["location"] == f"/login?next={EDITOR}", r.headers


async def test_relogin_falls_back_to_session_next():
    # The session-stashed destination (set on the bounce) drives the redirect
    # even when the form carries no ``next`` — the mechanism magic-link / SSO
    # rely on.
    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=False) as c:
        bounce = await c.get(EDITOR, headers={"Accept": "text/html"})
        assert bounce.status_code == 303
        r = await c.post("/login", data={
            "email": "demo-gm@example.com", "password": "demopass", "next": "/"})
        assert r.status_code == 303, r.text
        assert r.headers["location"] == EDITOR, r.headers


async def test_relogin_honours_form_next():
    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=False) as c:
        r = await c.post("/login", data={
            "email": "demo-gm@example.com", "password": "demopass", "next": EDITOR})
        assert r.status_code == 303
        assert r.headers["location"] == EDITOR, r.headers


async def test_open_redirect_is_scrubbed():
    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=False) as c:
        r = await c.post("/login", data={
            "email": "demo-gm@example.com", "password": "demopass",
            "next": "https://evil.example.com/phish"})
        assert r.status_code == 303
        assert r.headers["location"] == "/", r.headers  # external target rejected
