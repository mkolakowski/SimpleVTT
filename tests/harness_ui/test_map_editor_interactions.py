"""v2.775.0 — map editor object interactions: door click-toggle, copy/paste,
and drag-to-move (right-click menu).
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _walls(c, mid):
    return c.get(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls").json()["walls"]


def _open_editor(gm_page, mid):
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    expect(gm_page.locator("#me-overlay")).to_be_visible()
    gm_page.wait_for_timeout(400)


def _hit_box(gm_page):
    return gm_page.locator('#me-overlay line[stroke="transparent"]').first.bounding_box()


def test_door_click_toggles(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "d", "x1": 200, "y1": 200, "x2": 200, "y2": 360,
             "door": True, "open": False, "style": "wood"}]})
        try:
            _open_editor(gm_page, mid)
            box = _hit_box(gm_page)
            # Plain left-click on the door (view mode) toggles it open.
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["open"] is True, _walls(c, mid)
            # Click again → closed.
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["open"] is False
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_copy_paste_wall(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 300, "y2": 150, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            box = _hit_box(gm_page)
            # Right-click the wall → Copy.
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Copy").click()
            # Right-click an empty, visible part of the map (near the top, to
            # the right of the wall — the tall toolbar can push the centre off).
            ov = gm_page.locator("#me-overlay").bounding_box()
            gm_page.mouse.click(ov["x"] + ov["width"] * 0.6, ov["y"] + 110,
                                button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Paste").click()
            gm_page.wait_for_timeout(300)
            assert len(_walls(c, mid)) == 2, _walls(c, mid)
            assert all(w["style"] == "stone" for w in _walls(c, mid))
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_edit_wall_material(gm_page: Page) -> None:
    # v2.786.4 — material is set from the right-click menu directly (no prompt).
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 300, "y2": 150, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            box = _hit_box(gm_page)
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Wood").click()
            gm_page.wait_for_timeout(300)
            assert _walls(c, mid)[0]["style"] == "wood", _walls(c, mid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_right_click_works_in_draw_mode(gm_page: Page) -> None:
    # v2.781.1 — right-clicking an object while a draw tool is active must open
    # the menu, not start a drag that deletes the object on release.
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 320, "y2": 150, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            gm_page.locator("#me-wall-btn").click()   # enter wall (draw) mode
            box = _hit_box(gm_page)
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                button="right")
            # Menu opens…
            expect(gm_page.locator("#me-ctx-menu")).to_be_visible()
            assert gm_page.locator("#me-ctx-menu button", has_text="Delete").count() == 1
            # …and the wall was NOT deleted by a spurious grab.
            assert len(_walls(c, mid)) == 1, _walls(c, mid)
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_left_click_in_draw_mode_keeps_wall(gm_page: Page) -> None:
    # v2.783.2 — a plain click on a wall while a draw tool is active must NOT
    # delete it (removal is Erase-mode / right-click only).
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 320, "y2": 150, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            gm_page.locator("#me-wall-btn").click()   # enter wall (draw) mode
            box = _hit_box(gm_page)
            gm_page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            gm_page.wait_for_timeout(250)
            assert len(_walls(c, mid)) == 1, _walls(c, mid)  # still there
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})


def test_move_drags_object(gm_page: Page) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
        c.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
        mid = c.get(f"/api/campaign/{CAMPAIGN_ID}/active-map").json()["map_id"]
        c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": [
            {"id": "w", "x1": 150, "y1": 150, "x2": 300, "y2": 150, "style": "stone"}]})
        try:
            _open_editor(gm_page, mid)
            box = _hit_box(gm_page)
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            before = _walls(c, mid)[0]["x1"]
            # Right-click → Move, then press-drag the object down-right.
            gm_page.mouse.click(cx, cy, button="right")
            gm_page.locator("#me-ctx-menu button", has_text="Move").click()
            gm_page.mouse.move(cx, cy)
            gm_page.mouse.down()
            gm_page.mouse.move(cx + 120, cy + 120, steps=5)
            gm_page.mouse.up()
            gm_page.wait_for_timeout(300)
            after = _walls(c, mid)[0]
            assert after["x1"] != before or after["y1"] != 150, after  # it moved
        finally:
            c.put(f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/walls", json={"walls": []})
