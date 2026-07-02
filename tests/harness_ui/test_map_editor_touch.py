"""v2.837.0 — touch controls in the map editor (two-finger pinch-to-zoom)."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

# Dispatch a synthetic multi-touch gesture on #me-stage and return the zoom %
# before/after. Playwright has no high-level pinch, so we build TouchEvents.
_PINCH_JS = """(spread) => {
    const stage = document.getElementById('me-stage');
    const r = stage.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const mk = (x, y, id) => new Touch({ identifier: id, target: stage, clientX: x, clientY: y });
    const fire = (type, pts) => {
        const ts = pts.map((p, i) => mk(p[0], p[1], i));
        stage.dispatchEvent(new TouchEvent(type, {
            touches: type === 'touchend' ? [] : ts,
            changedTouches: ts, bubbles: true, cancelable: true }));
    };
    const pct = () => parseInt(document.getElementById('me-zoom-lbl').textContent);
    const before = pct();
    // Fingers start 40px apart, then move to `spread` px apart (pinch out = zoom in).
    fire('touchstart', [[cx - 20, cy], [cx + 20, cy]]);
    fire('touchmove',  [[cx - spread / 2, cy], [cx + spread / 2, cy]]);
    fire('touchend', []);
    return { before, after: pct() };
}"""


def test_two_finger_pinch_zooms(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)

    # Pinch OUT (fingers spread to 240px) → zoom in.
    out = gm_page.evaluate(_PINCH_JS, 240)
    assert out["after"] > out["before"], out

    # Pinch IN (fingers close to 20px) → zoom back out.
    inn = gm_page.evaluate(_PINCH_JS, 20)
    assert inn["after"] < inn["before"], inn
