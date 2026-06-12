"""v2.160.1 — legendary-actions Phase 1c demo fixture: the Adult Red
Dragon template is seeded so the v2.160.0 GM init-tracker legendary
strip has a real legendary creature to render on.

The Young Red Dragon (test_demo_dragon_spawn.py) is NOT legendary —
young dragons lack legendary actions RAW — so the strip had no demo
target. The Adult Red Dragon (CR 17) carries 3 legendary actions with
the v2.159.33 category+cost backfill, which the client's
``_ensureLegendaryActions`` reads from ``initData.templates[].sheet
.actions`` to build the spend buttons + 👑 pool meter.

These tests assert the template is seeded (via ``GET /templates``)
pointing at the ``adult-red-dragon`` SRD slug. The legendary-action
cost integers themselves are guarded by
test_monster_legendary_action_cost.py; the strip render is guarded by
tests/harness_ui/test_legendary_action_buttons.py.
"""
from .conftest import CAMPAIGN_ID


async def test_adult_red_dragon_template_seeded(gm_client):
    """The demo seed wires an Adult Red Dragon TokenTemplate the GM can
    drag-spawn from the Templates tab. It points at the SRD
    ``adult-red-dragon`` monster slug and tags sheet.type='dragon'."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    ard = next(
        (t for t in templates if t.get("name") == "Adult Red Dragon"),
        None,
    )
    assert ard is not None, (
        f"Adult Red Dragon template missing; got: "
        f"{[t.get('name') for t in templates]}"
    )
    sheet = ard.get("sheet") or {}
    assert sheet.get("monster_slug") == "adult-red-dragon", (
        f"Adult Red Dragon template must point at the 'adult-red-dragon' "
        f"SRD slug so its legendary actions project; got "
        f"{sheet.get('monster_slug')!r}"
    )
    assert sheet.get("type") == "dragon", (
        f"Adult Red Dragon template's sheet.type must be 'dragon'; got "
        f"{sheet.get('type')!r}"
    )


async def test_adult_red_dragon_sheet_page_renders(gm_client):
    """The monster-template sheet page (which projects via
    ``_monster_template_to_sheet``) renders for the seeded Adult Red
    Dragon — a smoke check that the slug resolves end-to-end so the
    legendary actions are present in the projected sheet."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    ard = next(
        (t for t in r.json() if t.get("name") == "Adult Red Dragon"),
        None,
    )
    assert ard is not None
    page = await gm_client.get(
        f"/campaign/{CAMPAIGN_ID}/monster-template/{ard['id']}/sheet"
    )
    assert page.status_code == 200, page.text
    assert "Adult Red Dragon" in page.text
