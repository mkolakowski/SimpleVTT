"""v2.759.0 — Maps 2.0 wall segment drag-to-move.

In GM wall-edit mode, dragging a segment translates both endpoints and saves;
a tap (no drag) deletes it. This drives a real pointer drag and asserts the
server-side wall moved.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def test_drag_moves_wall_segment(gm_page: Page) -> None:
    errors: list[str] = []
    gm_page.on("pageerror", lambda e: errors.append(str(e)))
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        # A vertical wall well inside the map.
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls",
              json={"walls": [{"id": "drag1", "x1": 300, "y1": 300,
                               "x2": 300, "y2": 420}]})
        try:
            gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
            gm_page.wait_for_function(
                "() => typeof window._onWallsUpdate === 'function'", timeout=8000)
            # Enter edit mode (so segments are draggable).
            gm_page.locator("#wall-edit-btn").click()
            # The wall arrives over the WS broadcast → renders (visible line +
            # transparent hit line). Wait for both, then drag the wide hit line.
            gm_page.wait_for_function(
                "() => document.querySelectorAll('#wall-overlay line').length >= 2",
                timeout=5000)
            hit = gm_page.locator('#wall-overlay line[stroke="transparent"]').first
            box = hit.bounding_box()
            assert box, "wall hit line should have a bounding box"
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            # Drag the segment ~90 screen px to the right.
            gm_page.mouse.move(cx, cy)
            gm_page.mouse.down()
            gm_page.mouse.move(cx + 90, cy, steps=6)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(400)  # let the PUT + WS settle

            moved = c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]
            assert len(moved) == 1, moved
            w = moved[0]
            # Both endpoints shifted right by roughly the same (positive) delta.
            assert w["x1"] > 320, w
            assert w["x2"] > 320, w
            assert abs((w["x1"] - 300) - (w["x2"] - 300)) < 5, w  # rigid move
            assert w["y1"] == 300 and w["y2"] == 420, w  # vertical drag = 0
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})

    assert not errors, f"JS errors: {errors}"
