"""GM access to all character sheets (TODO "GM Access to All Character Sheets").

The backend already supports this: `GET /campaign/{cid}/character/{char_id}/sheet`
(`character_sheet_page`) lets any campaign MEMBER view a character and the GM
(or owner) edit it — there's no ownership gate on viewing. The GM also reaches
it from three UI entry points (the Characters-drawer "Open full sheet →" link
shown for every PC, the init-tracker "📋 Sheet" link, and right-click-token).

These tests lock in the access contract so it can't silently regress:
  - the GM can load ANY campaign character's full sheet (incl. player-owned);
  - a non-GM member can view too (the view is member-wide);
  - an unknown character id → 404.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def test_gm_views_any_character_sheet(gm_client, roster):
    """The GM loads the full sheet page for characters they don't own."""
    for name in ("Pip Quickfingers", "Garrik Ironside", "Brakka Wildmane"):
        ch = roster.get(name)
        if not ch:
            continue
        r = await gm_client.get(
            f"/campaign/{CAMPAIGN_ID}/character/{ch['id']}/sheet")
        assert r.status_code == 200, (name, r.status_code)
        assert name.split()[0] in r.text  # the character's name renders


async def test_member_can_view_teammates_sheet(alice_client, roster):
    """A non-GM campaign member can also view a teammate's sheet (the view is
    member-wide; only editing is GM/owner-gated)."""
    pip = roster["Pip Quickfingers"]
    r = await alice_client.get(
        f"/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet")
    assert r.status_code == 200, r.text


async def test_unknown_character_sheet_404(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/character/99999999/sheet")
    assert r.status_code == 404, r.text
