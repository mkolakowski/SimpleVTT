"""Harness tests for the in-repo wiki routes.

Endpoint surface:
  GET /wiki              — landing page (Jinja-rendered)
  GET /wiki/{slug}       — serves docs/wiki/<slug>.{md,html}
  GET /wiki/doc/{slug}   — v2.49.9: serves plans / references / repo-root
                           docs via the _DOC_ALLOWLIST mapping

Happy-path: each route returns 200 with HTML content + a known marker
string (the page title for the landing, the version stamp for the
roll-log guide, the H1 for an allowlisted doc). Error-path: an unknown
slug 404s, a slug with directory-traversal characters 404s, and a slug
that isn't in the doc allowlist also 404s.
"""
import httpx

from .helpers import BASE_URL


async def test_wiki_home_renders():
    """GET /wiki — 200 + HTML body contains the page title."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "SimpleVTT wiki" in resp.text
    # Available-guides table includes the roll-log guide link.
    assert "/wiki/roll-log-guide" in resp.text
    # v2.49.9: the wiki nav menu is rendered on the landing too.
    assert 'class="wiki-nav"' in resp.text
    # v2.49.9: Plans + References + Repo docs sections all reachable.
    assert "/wiki/doc/plan-test-harness" in resp.text
    assert "/wiki/doc/changelog" in resp.text
    assert "/wiki/doc/roll-log-card-layout" in resp.text
    # v2.49.66: ruler/range plan listed in the design-plans table.
    assert "/wiki/doc/plan-ruler-and-range" in resp.text
    # v2.49.68: player simulacrum plan listed too.
    assert "/wiki/doc/plan-player-simulacrum" in resp.text
    # v2.49.103: spell-validation suite plan listed too.
    assert "/wiki/doc/plan-spell-validation-suite" in resp.text
    # v2.107.2: spell up-casting plan listed too.
    assert "/wiki/doc/plan-spell-upcasting" in resp.text
    # v2.49.118: Sorcery Points + Metamagic plan listed too.
    assert "/wiki/doc/plan-sorcery-points-and-metamagic" in resp.text
    # v2.49.119: Warlock Pact Boon plan listed too.
    assert "/wiki/doc/plan-warlock-pact-boon" in resp.text
    assert "/wiki/doc/plan-wild-magic" in resp.text
    assert "/wiki/doc/plan-eldritch-knight" in resp.text
    assert "/wiki/doc/plan-battle-master" in resp.text
    assert "/wiki/doc/plan-paladin-oaths" in resp.text
    # v2.158.71: magic-item automation plan listed (SRD audit P1).
    assert "/wiki/doc/plan-magic-items-automation" in resp.text
    # v2.158.72: exhaustion-levels plan listed (SRD audit P1).
    assert "/wiki/doc/plan-exhaustion-levels" in resp.text
    # v2.159.26: carrying-capacity plan listed (unblocks Bag of Holding).
    assert "/wiki/doc/plan-carrying-capacity" in resp.text
    # v2.159.32: legendary-actions plan listed (top P1 of 2026-06-11 SRD audit refresh).
    assert "/wiki/doc/plan-legendary-actions" in resp.text
    # v2.211.0: ability-score override plan listed (unblocks Belt of Giant Strength).
    assert "/wiki/doc/plan-str-override" in resp.text
    # v2.262.0: charged-items backlog plan listed.
    assert "/wiki/doc/plan-charged-items" in resp.text
    # v2.311.0: permanent ability-increase reconciliation plan listed.
    assert "/wiki/doc/plan-permanent-ability-increase-reconciliation" in resp.text
    # v2.49.167: PC vs NPC combat systems audit doc listed.
    assert "/wiki/pc-vs-npc-systems" in resp.text
    # v2.49.168: targeting system visual guide listed.
    assert "/wiki/targeting-system-guide" in resp.text
    # v2.49.182: Battle & Characters tab sheets visual guide listed.
    assert "/wiki/battle-character-sheets-guide" in resp.text
    # v2.49.185: unified mini-sheet plan listed.
    assert "/wiki/doc/plan-unified-mini-sheet" in resp.text
    # v2.49.186: unified mini-sheet visual mockups companion.
    assert "/wiki/unified-mini-sheet-mockups" in resp.text
    # v2.66.7: reactions-automation plan listed in the design-plans table.
    assert "/wiki/doc/plan-reactions-automation" in resp.text
    # v2.99.50: movement-OA flow plan listed in the design-plans table.
    assert "/wiki/doc/plan-movement-oa-flow" in resp.text
    # v2.99.386: full class-feature automation plan listed.
    assert "/wiki/doc/plan-full-feature-automation" in resp.text
    # v2.99.394: on-hit riders (automation Phase 2) sub-plan listed.
    assert "/wiki/doc/plan-on-hit-riders" in resp.text
    assert "/wiki/doc/plan-feature-saves" in resp.text
    assert "/wiki/doc/plan-temp-hp-and-bonuses" in resp.text
    assert "/wiki/doc/plan-auras" in resp.text
    assert "/wiki/doc/plan-movement-and-summons" in resp.text
    # v2.99.447: automation-coverage audit doc listed in the references table.
    assert "/wiki/doc/automation-coverage" in resp.text
    # v2.82.0: reactions-automation GM how-to listed in the available-guides table.
    assert "/wiki/reactions" in resp.text
    # v2.99.8: testing-checklist per-version verification log listed.
    assert "/wiki/testing-checklist" in resp.text
    # v2.151.3: TODONE completed-to-do archive listed in Repo documentation.
    assert "/wiki/doc/todone" in resp.text
    # v2.181.1: lair-actions + regional-effects catalog listed in available guides.
    assert "/wiki/lair-regional-catalog" in resp.text
    # v2.316.0: SRD automation-coverage banner rendered at top of landing page.
    assert "SRD 5e automation coverage" in resp.text
    assert 'id="srd-coverage"' in resp.text
    # v2.317.0 (assert tag): BUGS known-defect tracker listed in Repo documentation.
    assert "/wiki/doc/bugs" in resp.text


async def test_wiki_guide_serves_roll_log():
    """GET /wiki/roll-log-guide — 200 + body contains the version stamp
    the guide HTML carries at the top.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/roll-log-guide")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "roll-log" in resp.text.lower()
    # v2.49.9: standalone HTML guide gets the wiki nav menu injected
    # after <body> so navigation is consistent with the Jinja pages.
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_unknown_slug_404():
    """GET /wiki/no-such-page — 404."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/no-such-page")
    assert resp.status_code == 404


async def test_wiki_markdown_guide_renders():
    """v2.43.14: GET /wiki/realtime-broadcasts-catalog — markdown
    source file under docs/wiki/ is rendered through the markdown
    package + wrapped in the wiki_md.html template. 200 + body
    contains the catalog's title text + the v2.49.9 wiki nav.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/realtime-broadcasts-catalog")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Realtime broadcasts catalog" in resp.text
    assert "<h1" in resp.text
    assert "<table" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_reactions_guide_renders():
    """v2.82.0: GET /wiki/reactions — markdown GM how-to under
    docs/wiki/ rendered + wrapped + nav-injected. Confirms the
    reactions automation guide is reachable from the wiki.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/reactions")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 contains "Reactions Automation".
    assert "reactions" in resp.text.lower()
    assert "trigger event" in resp.text.lower()
    assert "<h1" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_lair_regional_catalog_renders():
    """v2.181.1: GET /wiki/lair-regional-catalog — markdown reference
    under docs/wiki/ rendered + wrapped + nav-injected. Catalogs each
    chromatic dragon lair's lair actions + regional effects (mirrors the
    app/content leaf modules)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/lair-regional-catalog")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 contains "Lair actions & regional effects catalog".
    assert "lair actions" in resp.text.lower()
    assert "regional effects" in resp.text.lower()
    # A known curated entry from the red dragon's volcanic lair.
    assert "Magma Erupts" in resp.text
    assert "<h1" in resp.text
    assert "<table" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_pc_vs_npc_systems_doc_renders():
    """v2.49.167: GET /wiki/pc-vs-npc-systems — markdown source under
    docs/wiki/ rendered + wrapped + nav-injected. Confirms the slug
    resolves to the new audit doc."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/pc-vs-npc-systems")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 contains "PC vs NPC combat systems".
    assert "pc vs npc" in resp.text.lower()
    assert "<h1" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_targeting_system_guide_renders():
    """v2.49.168: GET /wiki/targeting-system-guide — standalone HTML
    visual guide with inline SVG diagrams. 200 + body has the H1, the
    SVG diagrams, and the nav menu injected after <body>."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/targeting-system-guide")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "targeting system" in resp.text.lower()
    # Inline SVG diagrams are the whole point of this guide.
    assert "<svg" in resp.text
    # Standalone HTML gets the nav injected after <body>.
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_battle_character_sheets_guide_renders():
    """v2.49.182: GET /wiki/battle-character-sheets-guide — visual
    guide for the mini-sheet used in Battle + Characters drawer tabs.
    Includes mock-mini blocks, font samples, color swatches."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/battle-character-sheets-guide")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "battle" in resp.text.lower()
    assert "characters" in resp.text.lower()
    assert "mini-sheet" in resp.text.lower()
    # Standalone HTML gets the nav injected after <body>.
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_unified_mini_sheet_mockups_renders():
    """v2.49.186: GET /wiki/unified-mini-sheet-mockups — visual
    companion to the unified mini-sheet design plan. Renders the
    three architectural options as side-by-side .mock-mini blocks
    so a reviewer can scan layout differences."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/unified-mini-sheet-mockups")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The three mockups + summary table are the whole point.
    assert "conservative" in resp.text.lower()
    assert "symmetric" in resp.text.lower()
    assert "hybrid density" in resp.text.lower()
    # Standalone HTML gets the nav injected after <body>.
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_traversal_blocked():
    """Path-traversal characters in the slug are rejected before
    touching the filesystem.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/..%2Fpasswd")
    assert resp.status_code in (404, 400)


async def test_wiki_doc_serves_plan():
    """v2.49.9: GET /wiki/doc/plan-test-harness — 200 + body contains
    the plan's H1 + the nav menu. The route reads
    ``docs/plans/test-harness.md`` via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-test-harness")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The test-harness plan's H1 is "Autonomous click-through test harness — plan"
    assert "click-through" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_spell_upcasting_plan():
    """v2.107.2: GET /wiki/doc/plan-spell-upcasting — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/spell-upcasting.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-spell-upcasting")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "up-casting" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_full_feature_automation_plan():
    """v2.99.386: GET /wiki/doc/plan-full-feature-automation — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/full-feature-automation.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-full-feature-automation")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "automation" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_on_hit_riders_plan():
    """v2.99.394: GET /wiki/doc/plan-on-hit-riders — 200 + body contains
    the plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/on-hit-riders.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-on-hit-riders")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "rider" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_feature_saves_plan():
    """v2.99.405: GET /wiki/doc/plan-feature-saves — 200 + body contains
    the plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/feature-saves.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-feature-saves")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "saving throw" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_temp_hp_and_bonuses_plan():
    """v2.99.415: GET /wiki/doc/plan-temp-hp-and-bonuses — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/temp-hp-and-bonuses.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-temp-hp-and-bonuses")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "temp hp" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_auras_plan():
    """v2.99.424: GET /wiki/doc/plan-auras — 200 + body contains the
    plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/auras.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-auras")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "aura" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_movement_and_summons_plan():
    """v2.99.430: GET /wiki/doc/plan-movement-and-summons — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/movement-and-summons.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-movement-and-summons")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "summon" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_automation_coverage():
    """v2.99.447: GET /wiki/doc/automation-coverage — 200 + body contains
    the audit doc's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/automation-coverage.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/automation-coverage")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "automation coverage" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_simulacrum_plan():
    """v2.49.68: GET /wiki/doc/plan-player-simulacrum — 200 + body
    contains the plan's title + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/player-simulacrum.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-player-simulacrum")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "simulacrum" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_ruler_plan():
    """v2.49.66: GET /wiki/doc/plan-ruler-and-range — 200 + body
    contains the plan's H1 + the nav menu. The route reads
    ``docs/plans/ruler-and-range.md`` via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-ruler-and-range")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The plan's H1 is "Ruler & Range Enforcement — Design Plan".
    assert "ruler" in resp.text.lower()
    assert "range" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_reactions_automation_plan():
    """v2.66.7: GET /wiki/doc/plan-reactions-automation — 200 + body
    contains the plan's H1 + the nav menu. Resolves through
    _DOC_ALLOWLIST to ``docs/plans/reactions-automation.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-reactions-automation")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The plan's H1 is "Reactions Automation — Design Plan".
    assert "reactions automation" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_movement_oa_flow_plan():
    """v2.99.50: GET /wiki/doc/plan-movement-oa-flow — 200 + body
    contains the plan's H1 + the nav menu. Resolves through
    _DOC_ALLOWLIST to ``docs/plans/movement-oa-flow.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-movement-oa-flow")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The plan's H1 is "Movement-OA Flow — ...".
    assert "movement-oa flow" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_spell_validation_plan():
    """v2.49.103: GET /wiki/doc/plan-spell-validation-suite — 200 +
    body contains the plan's H1 + the nav menu. The route reads
    ``docs/plans/spell-validation-suite.md`` via the _DOC_ALLOWLIST
    mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-spell-validation-suite")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The plan's H1 contains "Spell-validation test suite".
    assert "spell-validation" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_sorcery_metamagic_plan():
    """v2.49.118: GET /wiki/doc/plan-sorcery-points-and-metamagic —
    200 + body contains the plan's H1 + the nav menu."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-sorcery-points-and-metamagic")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "sorcery points" in resp.text.lower()
    assert "metamagic" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_warlock_pact_boon_plan():
    """v2.49.119: GET /wiki/doc/plan-warlock-pact-boon — 200 +
    body contains the plan's H1 + the nav menu."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-warlock-pact-boon")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "pact boon" in resp.text.lower()
    assert "warlock" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_unified_mini_sheet_plan():
    """v2.49.185: GET /wiki/doc/plan-unified-mini-sheet — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/unified-mini-sheet.md``."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-unified-mini-sheet")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "unified mini-sheet" in resp.text.lower()
    # The plan has three ASCII mockups + a comparison matrix.
    assert "mockup" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_paladin_oaths_plan():
    """v2.99.245: GET /wiki/doc/plan-paladin-oaths — 200 + body
    contains the plan's H1 + the nav menu."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-paladin-oaths")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "paladin" in resp.text.lower()
    assert "ancients" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_battle_master_plan():
    """v2.99.233: GET /wiki/doc/plan-battle-master — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/battle-master.md``."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-battle-master")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "battle master" in resp.text.lower()
    assert "trip attack" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_eldritch_knight_plan():
    """v2.99.232: GET /wiki/doc/plan-eldritch-knight — 200 +
    body contains the plan's H1 + the nav menu. Resolves through
    the _DOC_ALLOWLIST to ``docs/plans/eldritch-knight.md``."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-eldritch-knight")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "eldritch knight" in resp.text.lower()
    assert "weapon bond" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_wild_magic_plan():
    """v2.99.227: GET /wiki/doc/plan-wild-magic — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/wild-magic.md``."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-wild-magic")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "wild magic" in resp.text.lower()
    assert "tides of chaos" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_root_doc():
    """v2.49.9: GET /wiki/doc/claude — 200 + body contains CLAUDE.md's
    H1 + the nav menu. The route reads ``CLAUDE.md`` from the repo
    root via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/claude")
    assert resp.status_code == 200
    assert "SimpleVTT" in resp.text
    assert "Claude Code guidelines" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_todone():
    """v2.151.3: GET /wiki/doc/todone — 200 + body contains the
    archive's H1 + the nav menu. The route reads ``TODONE.md`` from
    the repo root via the _DOC_ALLOWLIST mapping. The archive holds
    the items moved out of ``TODO.md`` once they shipped so the active
    backlog stays scannable.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/todone")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The archive's H1 is "SimpleVTT — Completed To-Dos".
    assert "completed to-dos" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_bugs():
    """v2.317.0: GET /wiki/doc/bugs — 200 + body contains the tracker's
    H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to ``BUGS.md``
    at the repo root. The tracker consolidates known defects that used to
    be scattered across TODO.md and inline plan-doc status notes."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/bugs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "bug tracker" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_magic_items_automation_plan():
    """v2.158.71: GET /wiki/doc/plan-magic-items-automation — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/magic-items-automation.md``. Filed
    by the 2026-06-10 SRD audit (TODO.md) as the top P1 gap: 292 SRD
    magic items shipped as data with empty ``actions`` arrays."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-magic-items-automation")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "magic-item automation" in resp.text.lower()
    assert "pearl of power" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_exhaustion_levels_plan():
    """v2.158.72: GET /wiki/doc/plan-exhaustion-levels — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/exhaustion-levels.md``. Filed by
    the 2026-06-10 SRD audit (TODO.md) as a P1 gap: engine treats
    Exhaustion as a single-flag buff, RAW has 6 cumulative levels."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-exhaustion-levels")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "exhaustion levels" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_carrying_capacity_plan():
    """v2.159.26: GET /wiki/doc/plan-carrying-capacity — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/carrying-capacity.md``. Filed to
    unblock Bag of Holding (RAW DMG p.153) — needs STR × 15 carry-
    capacity engine to discount."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-carrying-capacity")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "carrying capacity" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_legendary_actions_plan():
    """v2.159.32: GET /wiki/doc/plan-legendary-actions — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/legendary-actions.md``. Top P1
    of the 2026-06-11 SRD audit refresh — 15 SRD monsters carry
    legendary-action data in their unified ``actions`` array but
    the engine has no /use_legendary_action dispatch."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-legendary-actions")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "legendary actions" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_str_override_plan():
    """v2.211.0: GET /wiki/doc/plan-str-override — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/str-override.md``. Filed to
    unblock Belt of Giant Strength (DMG p.155) + Amulet of Health
    (DMG p.150) + Potion of Giant Strength (DMG p.187) — needs an
    effective-ability-score override substrate (max(base, set))."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-str-override")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "ability-score override" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_charged_items_plan():
    """v2.262.0: GET /wiki/doc/plan-charged-items — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/charged-items.md``. Backlog plan
    for extending the existing charge/recharge substrate to the
    remaining SRD charged items (Staff of Power, Ring of the Ram,
    Gem of Seeing, Wand of Wonder, etc.)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-charged-items")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "charged magic items" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_permanent_ability_increase_reconciliation_plan():
    """v2.311.0: GET /wiki/doc/plan-permanent-ability-increase-reconciliation
    — 200 + body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/permanent-ability-increase-reconciliation.md``.
    Reconciles the two parallel Manuals & Tomes dispatch paths (v2.222.0
    permanent_boost vs. v2.308.0 ability_increase)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get(
            "/wiki/doc/plan-permanent-ability-increase-reconciliation",
        )
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "permanent ability-increase reconciliation" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_unknown_slug_404():
    """v2.49.9: a slug that isn't in _DOC_ALLOWLIST 404s. Important
    security guarantee — the allowlist is the only way to reach a
    file outside ``docs/wiki/``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/not-in-allowlist")
    assert resp.status_code == 404


async def test_wiki_doc_traversal_blocked():
    """v2.49.9: directory-traversal characters in the doc slug are
    rejected by the slug guard before the allowlist lookup.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/..%2Fconfig")
    assert resp.status_code in (404, 400)
