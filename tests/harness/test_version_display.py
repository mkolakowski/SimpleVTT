"""v2.776.0 — version-stamp display toggles.

`/version` now also reports the release "Fun Name", and the masthead/footer
stamp is gated by SHOW_VERSION / VERSION_LINK_CHANGELOG / SHOW_VERSION_NAME.
The harness app runs with all three at their default (true), so the rendered
chrome shows the number, the fun name, and a link to the wiki changelog.
"""
from __future__ import annotations

import httpx
import pytest

from .helpers import BASE_URL


@pytest.mark.asyncio
async def test_version_endpoint_reports_name() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        r = await c.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["app_version"], body
    # v2.776.0 — the fun name is now part of the contract.
    assert isinstance(body["app_version_name"], str) and body["app_version_name"], body


@pytest.mark.asyncio
async def test_footer_stamp_links_changelog_and_shows_name() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        ver = (await c.get("/version")).json()
        # The login page renders base.html chrome (footer + masthead).
        html = (await c.get("/login")).text
    # Default config (all toggles true): the version + fun name show, and the
    # stamp links to the wiki changelog.
    assert f"v{ver['app_version']}" in html
    assert ver["app_version_name"] in html
    assert '/wiki/doc/changelog' in html
