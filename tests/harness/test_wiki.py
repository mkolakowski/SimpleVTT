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
import re

import httpx

from .helpers import BASE_URL


def _guide_sort_key(title: str) -> str:
    """Same ordering the wiki guides table is kept in: case-insensitive,
    a leading 'The ' ignored."""
    t = title.strip().lower()
    return t[4:] if t.startswith("the ") else t


async def test_wiki_home_renders():
    """GET /wiki — 200 + the landing page's guides / references / repo-docs /
    banners. v2.630.0: the (large) design-plans table moved to /wiki/plans, so
    the landing page links out to it instead of listing every plan."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "SimpleVTT wiki" in resp.text
    # Available-guides table.
    assert "/wiki/roll-log-guide" in resp.text
    assert "/wiki/demo-content" in resp.text       # v2.597.0
    assert "/wiki/admin-center" in resp.text        # v2.483.0
    assert "/wiki/backups" in resp.text             # v2.628.0
    assert "/wiki/pc-vs-npc-systems" in resp.text   # v2.49.167
    assert "/wiki/fail2ban-deployment" in resp.text # v2.476.0
    assert "/wiki/privacy" in resp.text             # v2.478.0
    assert "/wiki/targeting-system-guide" in resp.text
    assert "/wiki/battle-character-sheets-guide" in resp.text
    assert "/wiki/unified-mini-sheet-mockups" in resp.text
    assert "/wiki/reactions" in resp.text
    assert "/wiki/testing-checklist" in resp.text
    assert "/wiki/lair-regional-catalog" in resp.text
    assert "/wiki/srd-races-implementation" in resp.text
    assert "/wiki/srd-conditions" in resp.text
    assert "/wiki/player-onboarding" in resp.text   # v2.634.0
    assert "/wiki/inviting-players" in resp.text     # v2.635.0
    assert "/wiki/theming" in resp.text              # v2.636.0
    assert "/wiki/map-editor-tour" in resp.text        # v2.841.0
    assert "/wiki/maps-grids-tokens" in resp.text     # v2.637.0
    assert "/wiki/building-an-encounter" in resp.text # v2.639.0
    # v2.638.0: audience filter buttons on the guides table + the Format
    # column was dropped from the landing-page doc-tables.
    assert 'class="aud-filter"' in resp.text
    assert 'data-aud-filter="players"' in resp.text
    assert 'data-aud-filter="gms"' in resp.text
    assert 'id="guides-table"' in resp.text
    assert "<th>Format</th>" not in resp.text
    # v2.638.1: the guides table is kept in alphabetical order.
    m = re.search(r'id="guides-table".*?</table>', resp.text, re.S)
    assert m, "guides table not found"
    import html as _html
    titles = [_html.unescape(t) for t in re.findall(r'<a href="/wiki/[^"]+">([^<]+)</a>', m.group(0))]
    assert len(titles) >= 20
    assert titles == sorted(titles, key=_guide_sort_key), f"guides not alphabetical: {titles}"
    # v2.49.9: the wiki nav menu is rendered on the landing too.
    assert 'class="wiki-nav"' in resp.text
    # v2.630.0: the design-plans index moved to its own page; the landing
    # page links out to it rather than listing every plan inline.
    assert "/wiki/plans" in resp.text
    # References + Repo documentation sections stay on the landing page.
    assert "/wiki/doc/changelog" in resp.text
    assert "/wiki/doc/roll-log-card-layout" in resp.text
    assert "/wiki/doc/automation-coverage" in resp.text         # v2.99.447
    assert "/wiki/doc/condition-enforcement-audit" in resp.text # v2.384.0
    assert "/wiki/doc/todone" in resp.text                      # v2.151.3
    assert "/wiki/doc/bugs" in resp.text                        # v2.317.0
    # Banners at the top of the landing page.
    assert "SRD 5e automation coverage" in resp.text            # v2.316.0
    assert 'id="srd-coverage"' in resp.text
    # v2.630.4: the SRD automation breakdown is collapsed behind a click.
    assert '<details class="srd-coverage"' in resp.text
    assert "<summary" in resp.text
    assert "Security spine" in resp.text                        # v2.423.7
    assert 'id="security-spine"' in resp.text
    # v2.630.3: the doc-listing tables use the compact emoji-only Status column
    # (full text moved to a hover title) + the doc-table layout class.
    assert 'class="doc-table"' in resp.text
    assert 'class="status-shipped" title="' in resp.text


async def test_wiki_plans_page_renders():
    """v2.630.0: GET /wiki/plans — the design-plans index split off the landing
    page to de-clutter it. 200 + the nav + a back-link + the plans table (a
    representative spread of plan links, the shipped-status badge styling, and
    many entries)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/plans")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Design plans" in resp.text
    assert 'class="wiki-nav"' in resp.text
    assert 'href="/wiki"' in resp.text          # back-link to the index
    # A representative spread of plans now lives here (and not on /wiki).
    for slug in (
        "plan-test-harness", "plan-ruler-and-range", "plan-legendary-actions",
        "plan-race-features", "plan-full-feature-automation",
        "plan-notes-and-handouts", "plan-app-wide-roles-and-storage",
        "plan-pending-resolution-state-machine", "plan-backup-export-overhaul",
        "plan-spell-upcasting", "plan-reactions-automation",
        "plan-campaign-stats", "plan-vision-and-light",
    ):
        assert f"/wiki/doc/{slug}" in resp.text, f"plans page missing {slug}"
    # The styled status badges render (the table carries status spans).
    assert "status-shipped" in resp.text
    # It's the full index, not a handful.
    assert resp.text.count("/wiki/doc/plan-") >= 30


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


async def test_wiki_guide_serves_demo_content():
    """v2.597.0 — GET /wiki/demo-content serves the demo catalog (the five
    leveled sample campaigns + the collapsed generation-prompts section)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/demo-content")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    text = resp.text
    assert "Demo content" in text
    # All five active leveled campaigns are catalogued, plus the archived
    # original L5 (Sundered Vault, kept as the harness anchor + archive demo).
    for name in ("Goblin Warrens", "Catacombs", "Sundered Vault", "Saltmarsh", "Shadowfell Spire", "Apotheosis"):
        assert name in text, f"demo-content guide missing {name!r}"
    # The collapsed generation-prompts section is present.
    assert "Generation prompts" in text and "<details>" in text
    assert 'class="wiki-nav"' in text


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


async def test_wiki_backups_guide_renders():
    """v2.628.0: GET /wiki/backups — markdown how-to under docs/wiki/ rendered
    + wrapped + nav-injected. Describes the operator backup sidecar (the three
    artifacts + download zip structure) and the in-app campaign/PC/homebrew
    exports."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/backups")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "backups" in resp.text.lower() and "restore" in resp.text.lower()
    # The download-structure section names the three operator artifacts.
    assert ".sql.gz" in resp.text
    assert ".homebrew.tar.gz" in resp.text
    assert ".uploads.tar.gz" in resp.text
    # v2.630.1: the guide spells out the campaign-play content captured in the
    # DB dump (PCs / campaigns / notes / …).
    body_lower = resp.text.lower()
    assert "what campaign content is captured" in body_lower
    assert "player character" in body_lower
    assert "notes &amp; handouts" in body_lower or "notes & handouts" in body_lower
    # v2.630.2: the tarball-internals breakdown + the cross-format answer.
    assert "inside the tarballs" in body_lower
    assert "encounter_bg" in resp.text          # an uploads-bucket folder
    assert "campaign-&lt;id&gt;" in resp.text or "campaign-<id>" in resp.text
    assert "in-app import tools" in body_lower   # the cross-format Q&A
    assert "<h1" in resp.text
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


async def test_wiki_map_editor_tour_guide_renders():
    """v2.841.0: GET /wiki/map-editor-tour — markdown GM how-to under
    docs/wiki/ rendered + wrapped + nav-injected. Tours the map editor's
    element families using the furnished demo maps as worked examples."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/map-editor-tour")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 + a couple of element families the tour catalogs.
    assert "map editor tour" in resp.text.lower()
    assert "fog of war" in resp.text.lower()
    assert "secret" in resp.text.lower()          # secret-door callout
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


async def test_wiki_fail2ban_deployment_guide_renders():
    """v2.476.0: GET /wiki/fail2ban-deployment — markdown source
    under docs/wiki/ rendered + wrapped + nav-injected. Closes the
    Phase 4 fail2ban arc per the doc-surfacing rule in
    CLAUDE.md."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/fail2ban-deployment")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 contains "fail2ban deployment".
    assert "fail2ban deployment" in resp.text.lower()
    assert "<h1" in resp.text
    assert 'class="wiki-nav"' in resp.text
    # Spot-check that a key operator step is present (the threshold
    # tuning section). Anchors against a future edit that
    # accidentally truncates the guide.
    assert "FAIL2BAN_LOGIN_MAXRETRY" in resp.text


async def test_wiki_privacy_doc_renders():
    """v2.478.0: GET /wiki/privacy — markdown source under
    docs/wiki/ rendered + wrapped + nav-injected. Privacy policy
    page surfaced through the wiki per the doc-surfacing rule in
    CLAUDE.md.

    v2.479.0: page rewritten as a GDPR Article 12–14 compliant
    privacy notice. Content anchors below enforce that the
    GDPR-required sections + the prior factual catalog both
    stay present."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/privacy")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1 contains "Privacy".
    assert "privacy" in resp.text.lower()
    assert "<h1" in resp.text
    assert 'class="wiki-nav"' in resp.text
    # Operator-controlled env-var references stay anchored.
    assert "AUDIT_LOG_PATH" in resp.text, (
        "privacy doc missing AUDIT_LOG_PATH env var reference"
    )
    assert "TRUSTED_PROXY_HOPS" in resp.text, (
        "privacy doc missing TRUSTED_PROXY_HOPS env var reference"
    )
    # The events catalog must reference the canonical event tags.
    assert "api.not_found" in resp.text, (
        "privacy doc missing api.not_found event in the catalog"
    )
    # v2.479.0 — GDPR-required sections must all be present.
    # If a future edit drops one, the test fails before the
    # operator unwittingly publishes a non-compliant policy.
    body_lower = resp.text.lower()
    for anchor in (
        "controller",            # Section 1 — controller info
        "legal basis",           # Sections 2.1–2.6 + recipients
        "article 6",             # Lawful processing reference
        "article 15",            # Right of access
        "article 17",            # Right to erasure
        "article 20",            # Right to data portability
        "article 22",            # Automated decision-making
        "supervisory authority", # Right to lodge a complaint
        "automated decision",    # Section 4 — fail2ban disclosure
        "data breach",           # Section 8 — Article 33-34
    ):
        assert anchor in body_lower, (
            f"privacy doc missing GDPR-required anchor {anchor!r}; "
            f"page may have dropped a required section"
        )


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


async def test_wiki_doc_serves_exploration_fog_plan():
    """v2.843.0: GET /wiki/doc/plan-exploration-fog — 200 + body contains the
    plan's H1 + the nav menu. Resolves through _DOC_ALLOWLIST to
    ``docs/plans/exploration-fog.md``."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-exploration-fog")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "exploration-tracking fog" in resp.text.lower()
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


async def test_wiki_doc_serves_vision_plan():
    """v2.703.0: GET /wiki/doc/plan-vision-and-light — 200 + body contains
    the plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/vision-and-light.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-vision-and-light")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "vision" in resp.text.lower() and "light" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_spell_utility_upcast_plan():
    """v2.404.10: GET /wiki/doc/plan-spell-utility-upcast — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/spell-utility-upcast.md``. Closure
    retrospective for the v2.404.1 → v2.404.9 spell utility-upcast arc
    that closed 9 target-scaling utility spells across both
    `_SPELL_BUFF_MAP` and `_SPELL_TARGET_CAPS` substrates.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-spell-utility-upcast")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "spell utility-upcast" in resp.text.lower()
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


async def test_wiki_doc_serves_aura_geometry_enforcement_plan():
    """v2.515.0: GET /wiki/doc/plan-aura-geometry-enforcement — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/aura-geometry-enforcement.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-aura-geometry-enforcement")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "geometry enforcement" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_conjure_family_plan():
    """v2.538.0: GET /wiki/doc/plan-conjure-family — 200 + body contains
    the plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/conjure-family.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-conjure-family")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "conjure family" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_notes_and_handouts_plan():
    """v2.553.2: GET /wiki/doc/plan-notes-and-handouts — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/notes-and-handouts.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-notes-and-handouts")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "notes &amp; handouts" in resp.text.lower() or "notes & handouts" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_aoe_enter_trigger_plan():
    """v2.566.2: GET /wiki/doc/plan-aoe-enter-trigger — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/aoe-enter-trigger.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-aoe-enter-trigger")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "enter-trigger" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_homebrew_fork_srd_plan():
    """v2.568.4: GET /wiki/doc/plan-homebrew-fork-srd — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/homebrew-fork-srd.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-homebrew-fork-srd")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "homebrew" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_admin_center_consolidation_plan():
    """v2.573.1: GET /wiki/doc/plan-admin-center-consolidation — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/admin-center-consolidation.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-admin-center-consolidation")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "admin center" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_app_wide_roles_plan():
    """v2.584.0: GET /wiki/doc/plan-app-wide-roles-and-storage — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/app-wide-roles-and-storage.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-app-wide-roles-and-storage")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "roles" in resp.text.lower() and "storage" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_pending_resolution_plan():
    """v2.610.1: GET /wiki/doc/plan-pending-resolution-state-machine — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/pending-resolution-state-machine.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-pending-resolution-state-machine")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "pending-resolution" in resp.text.lower() or "resolution" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_campaign_stats_plan():
    """v2.649.1: GET /wiki/doc/plan-campaign-stats — 200 + body contains
    the plan's H1 + the nav menu. Resolves through the _DOC_ALLOWLIST to
    ``docs/plans/campaign-stats.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-campaign-stats")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "statistics" in resp.text.lower() or "stat" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_campaign_pc_archive_plan():
    """v2.602.1: GET /wiki/doc/plan-campaign-pc-archive — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/campaign-pc-archive.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-campaign-pc-archive")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "archive" in resp.text.lower() and "retire" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_backup_export_overhaul_plan():
    """v2.612.4: GET /wiki/doc/plan-backup-export-overhaul — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/backup-export-overhaul.md``. Phase 0
    of the backup/export-import arc: zip exports at PC / campaign /
    homebrew-item levels, a clone-or-restore importer, export rate-limit,
    a progress toast, and operator backup settings in the Admin Center.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-backup-export-overhaul")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "backup" in resp.text.lower() and "export-import" in resp.text.lower()
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


async def test_wiki_doc_serves_condition_enforcement_audit():
    """v2.384.0: GET /wiki/doc/condition-enforcement-audit — 200 + body
    contains the audit's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/condition-enforcement-audit.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/condition-enforcement-audit")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # H1: "Condition enforcement audit — Charmed / Grappled / Incapacitated"
    assert "condition enforcement audit" in resp.text.lower()
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


async def test_wiki_doc_serves_demo_magic_link_plan():
    """v2.423.3: GET /wiki/doc/plan-demo-magic-link — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/demo-magic-link.md``. Proposes
    URL-based passwordless login for the demo instance only, behind
    a double-env-var gate (SIMPLEVTT_DEMO_MODE + a separate
    SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED), single-use HMAC tokens,
    canonical log lines for the fail2ban/CrowdSec sibling TODO."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-demo-magic-link")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "demo magic-link" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_fail2ban_crowdsec_integration_plan():
    """v2.423.4: GET /wiki/doc/plan-fail2ban-crowdsec-integration — 200
    + body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/fail2ban-crowdsec-integration.md``.
    Proposes canonical structured log lines + reference fail2ban
    filter.d/jail.d configs + reference CrowdSec parsers/scenarios
    configs shipped in-repo under docs/integrations/, with a Phase 2
    compose-side smoke test that drives a real CrowdSec container."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-fail2ban-crowdsec-integration")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "fail2ban" in resp.text.lower()
    assert "crowdsec" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_cast_and_broadcast_tail_plan():
    """v2.436.0: GET /wiki/doc/plan-cast-and-broadcast-tail — 200 +
    body contains the plan's H1 + the nav menu. Resolves through
    the _DOC_ALLOWLIST to ``docs/plans/cast-and-broadcast-tail.md``.
    Plan opens an arc for mechanizing Bucket A utility spells
    (True Strike, Find Steed, Speak with Animals, Pass Without
    Trace, Spider Climb) that currently cast + broadcast without
    a server-side effect."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-cast-and-broadcast-tail")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "cast-and-broadcast" in resp.text.lower()
    assert "true strike" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_cloudflare_edge_banning_plan():
    """v2.423.5: GET /wiki/doc/plan-cloudflare-edge-banning — 200 +
    body contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/cloudflare-edge-banning.md``.
    Proposes outbound Cloudflare API client + GM-only "Ban IP at
    edge" button + admin-audit log, with a wiremock service in
    docker-compose for dev testing per the third-party-API rule.
    Closes the three-piece security spine started in v2.423.2."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-cloudflare-edge-banning")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "cloudflare" in resp.text.lower()
    assert "edge-banning" in resp.text.lower() or "edge banning" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_admin_center_mfa_plan():
    """v2.485.8: GET /wiki/doc/plan-admin-center-mfa — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/admin-center-mfa.md``. Proposes an
    opt-in TOTP second factor on the admin-center login plus an
    env-set recovery code whose blank default accepts nothing."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-admin-center-mfa")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "totp" in resp.text.lower()
    assert "recovery code" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_race_features_plan():
    """v2.393.0: GET /wiki/doc/plan-race-features — 200 + body
    contains the plan's H1 + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/race-features.md``. Closes the
    SRD Races row from ~90% → ~100% via 7 phase ships on top of the
    v2.392.0 Dragonborn Breath Weapon."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-race-features")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "race features" in resp.text.lower()
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
