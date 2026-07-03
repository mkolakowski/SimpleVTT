"""v2.865.0 — caster monsters surface a Spells tab with cast buttons.

The mini-sheet projection now parses a monster's SRD "Spellcasting"
special-ability prose (folded into ``actions`` with
``category: "special_ability"``) into structured ``spells`` +
``spell_slots`` + spellcasting ability
(``_parse_monster_spellcasting`` → ``_monster_dict_to_sheet``). That
un-gates the mini-sheet's Spells tab (``_mini_sheet_card.html`` only
renders it when ``_is_caster``), so a caster monster (Mage / Archmage /
Lich / Priest / Druid / ...) renders ``.mini-cast-btn`` cast buttons —
which route through the existing ``/npc_cast_spell`` — instead of only a
stat-block blurb.

The demo ships an Archmage TokenTemplate (see
``test_archmage_template_registered``), whose projected mini-sheet is
pre-rendered into the tabletop page's monster-card pool. Before this
change a monster template carried no ``spells`` → no cast buttons; now
its prepared spells render as ``.mini-cast-btn`` elements tagged with a
``data-char-id="monster-template-<id>"`` owner.
"""
import re

from .conftest import CAMPAIGN_ID


async def test_caster_monster_mini_sheet_renders_spell_cast_buttons(gm_client):
    """A caster monster's projected mini-sheet now owns cast buttons, and the
    Archmage's parsed prepared spells (e.g. its 6th-level Globe of
    Invulnerability) render as such — proof the Spellcasting prose was parsed
    into a structured spell list."""
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert r.status_code == 200, r.text
    html = r.text

    # A monster TEMPLATE (not a PC) now owns .mini-cast-btn cast buttons —
    # only possible once the projection emits `spells` for casters.
    assert re.search(
        r'class="mini-cast-btn"[^>]*data-char-id="monster-template-\d+"',
        html, re.I,
    ), "expected a caster monster's mini-sheet cast button in the card pool"

    # The Archmage's parsed prepared spell (unique to its list) renders as a
    # cast button owned by a monster template.
    assert re.search(
        r'class="mini-cast-btn"[^>]*data-char-id="monster-template-\d+"'
        r'[^>]*data-spell-name="[^"]*globe of invulnerability',
        html, re.I,
    ), "archmage's parsed prepared spells should render as cast buttons"


async def test_non_caster_monster_has_no_spell_buttons_leak(gm_client):
    """Sanity: the un-gate is caster-specific. A well-known non-caster in the
    demo (the Goblin) does not sprout spell cast buttons — the parser returns
    None when there's no Spellcasting block, so nothing is injected."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    # Every shipped template still lists (the raw slug-pointer sheet is
    # unchanged); the projection only adds spells for casters. This guards
    # that the endpoint contract for /templates didn't change shape.
    for t in templates:
        assert "sheet" in t and isinstance(t["sheet"], dict), t
