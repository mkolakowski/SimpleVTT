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
    # v2.597.0: the demo-content catalog is surfaced in the guides table.
    assert "/wiki/demo-content" in resp.text
    # v2.483.0: the Admin Center guide is surfaced in the guides table.
    assert "/wiki/admin-center" in resp.text
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
    # v2.404.10: spell utility-upcast arc closure retrospective listed.
    assert "/wiki/doc/plan-spell-utility-upcast" in resp.text
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
    # v2.476.0: fail2ban deployment operator guide listed.
    assert "/wiki/fail2ban-deployment" in resp.text
    # v2.478.0: privacy reference listed.
    assert "/wiki/privacy" in resp.text
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
    # v2.515.0: aura & barrier geometry enforcement plan listed.
    assert "/wiki/doc/plan-aura-geometry-enforcement" in resp.text
    # v2.538.0: conjure-family summon-catalog plan listed.
    assert "/wiki/doc/plan-conjure-family" in resp.text
    # v2.553.2: notes & handouts (E2E-encrypted player notes) plan listed.
    assert "/wiki/doc/plan-notes-and-handouts" in resp.text
    # v2.566.2: persistent-AoE enter-trigger plan listed.
    assert "/wiki/doc/plan-aoe-enter-trigger" in resp.text
    # v2.568.4: fork-&-tweak-SRD-as-homebrew plan listed.
    assert "/wiki/doc/plan-homebrew-fork-srd" in resp.text
    # v2.573.1: admin-center-consolidation plan listed.
    assert "/wiki/doc/plan-admin-center-consolidation" in resp.text
    # v2.584.0: app-wide-roles-and-storage plan listed.
    assert "/wiki/doc/plan-app-wide-roles-and-storage" in resp.text
    # v2.602.1: campaign & PC archive plan listed.
    assert "/wiki/doc/plan-campaign-pc-archive" in resp.text
    assert "/wiki/doc/plan-movement-and-summons" in resp.text
    # v2.99.447: automation-coverage audit doc listed in the references table.
    assert "/wiki/doc/automation-coverage" in resp.text
    # v2.384.0: condition-enforcement audit doc listed in the references table.
    assert "/wiki/doc/condition-enforcement-audit" in resp.text
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
    # v2.393.0: race-features plan listed (closes the SRD Races row to ~100%).
    assert "/wiki/doc/plan-race-features" in resp.text
    # v2.423.3: demo magic-link login plan listed (URL-login for demo instance only).
    assert "/wiki/doc/plan-demo-magic-link" in resp.text
    # v2.423.4: fail2ban/CrowdSec log integration plan listed.
    assert "/wiki/doc/plan-fail2ban-crowdsec-integration" in resp.text
    # v2.423.5: Cloudflare edge-banning integration plan listed.
    assert "/wiki/doc/plan-cloudflare-edge-banning" in resp.text
    assert "/wiki/doc/plan-admin-center-mfa" in resp.text
    # v2.436.0: cast-and-broadcast tail plan listed.
    assert "/wiki/doc/plan-cast-and-broadcast-tail" in resp.text
    # v2.423.7: Security spine banner rendered at the top of the landing page.
    assert "Security spine" in resp.text
    assert 'id="security-spine"' in resp.text
    # v2.400.0: SRD race rules implementation guide listed in Available guides.
    assert "/wiki/srd-races-implementation" in resp.text
    # v2.402.0: SRD conditions implementation guide listed in Available guides.
    assert "/wiki/srd-conditions" in resp.text


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
    # All five leveled campaigns are catalogued.
    for name in ("Goblin Warrens", "Sundered Vault", "Saltmarsh", "Shadowfell Spire", "Apotheosis"):
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
