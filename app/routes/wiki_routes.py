"""In-repo wiki routes.

Serves the wiki landing page (``/wiki``) and the documentation surface:
  - ``/wiki/<slug>``       — guides under ``docs/wiki/`` (``.md`` or ``.html``).
  - ``/wiki/doc/<slug>``   — plans / references / repo-root docs via the
                             v2.49.9 ``_DOC_ALLOWLIST`` mapping.

Read-only, no auth — the content is reference documentation,
deliberately not gated. Lives in its own router so the route list
stays organized.

To add a new guide:
  1. Drop ``docs/wiki/<slug>.html`` or ``docs/wiki/<slug>.md`` into the repo.
  2. Add an entry in ``app/templates/wiki.html``'s "Available guides"
     table linking to ``/wiki/<slug>``.
  3. Add the same entry in ``docs/wiki/README.md`` so the on-disk index
     stays in sync.

To surface a new plan / reference / root doc:
  1. Add a row to ``_DOC_ALLOWLIST`` below mapping a slug to the file
     path (relative to repo root).
  2. Add a row to the matching table in ``app/templates/wiki.html``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import markdown as md_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..database import get_db
from ..models import User
from ..templates import templates

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WIKI_DIR = _REPO_ROOT / "docs" / "wiki"

# v2.49.9: allowlist of plans / references / repo-root docs reachable
# through the wiki nav. Slug → path-relative-to-repo-root. Keep the
# slugs lowercase + hyphenated to match the URL pattern at
# ``/wiki/doc/<slug>``. ``plan-*`` prefix marks docs/plans/ entries;
# bare slugs are either docs/ refs or repo root.
_DOC_ALLOWLIST: dict[str, Path] = {
    # Repo root
    "readme": Path("README.md"),
    "changelog": Path("CHANGELOG.md"),
    "changelog-v1": Path("CHANGELOG_v1.md"),
    "claude": Path("CLAUDE.md"),
    "credits": Path("CREDITS.md"),
    "todo": Path("TODO.md"),
    "todone": Path("TODONE.md"),
    "bugs": Path("BUGS.md"),
    # docs/ references
    "roll-log-card-layout": Path("docs") / "roll-log-card-layout.md",
    "test-harness-coverage": Path("docs") / "test-harness-coverage.md",
    "automation-coverage": Path("docs") / "automation-coverage.md",
    "image-prompts": Path("docs") / "demo" / "image-prompts.md",
    # v2.384.0 — Condition-enforcement audit (Charmed / Grappled /
    # Incapacitated partial-clause review). Surfaced via /wiki for
    # contributors planning to close the per-clause gaps.
    "condition-enforcement-audit": Path("docs") / "condition-enforcement-audit.md",
    # docs/plans/ design docs
    "plan-advantage-disadvantage": Path("docs") / "plans" / "advantage-disadvantage.md",
    "plan-class-content-status": Path("docs") / "plans" / "class-content-status.md",
    "plan-full-feature-automation": Path("docs") / "plans" / "full-feature-automation.md",
    "plan-on-hit-riders": Path("docs") / "plans" / "on-hit-riders.md",
    "plan-feature-saves": Path("docs") / "plans" / "feature-saves.md",
    "plan-temp-hp-and-bonuses": Path("docs") / "plans" / "temp-hp-and-bonuses.md",
    "plan-auras": Path("docs") / "plans" / "auras.md",
    "plan-movement-and-summons": Path("docs") / "plans" / "movement-and-summons.md",
    "plan-death-saves": Path("docs") / "plans" / "death-saves.md",
    "plan-demo-mode": Path("docs") / "plans" / "demo-mode.md",
    "plan-encounter-sim-test-suite": Path("docs") / "plans" / "encounter-sim-test-suite.md",
    "plan-movement-oa-flow": Path("docs") / "plans" / "movement-oa-flow.md",
    "plan-player-simulacrum": Path("docs") / "plans" / "player-simulacrum.md",
    "plan-reactions-automation": Path("docs") / "plans" / "reactions-automation.md",
    "plan-ruler-and-range": Path("docs") / "plans" / "ruler-and-range.md",
    "plan-sorcery-points-and-metamagic": Path("docs") / "plans" / "sorcery-points-and-metamagic.md",
    "plan-spell-upcasting": Path("docs") / "plans" / "spell-upcasting.md",
    "plan-spell-validation-suite": Path("docs") / "plans" / "spell-validation-suite.md",
    "plan-warlock-pact-boon": Path("docs") / "plans" / "warlock-pact-boon.md",
    "plan-test-harness": Path("docs") / "plans" / "test-harness.md",
    "plan-unified-mini-sheet": Path("docs") / "plans" / "unified-mini-sheet.md",
    "plan-wiki-expansion": Path("docs") / "plans" / "wiki-expansion.md",
    "plan-wild-magic": Path("docs") / "plans" / "wild-magic.md",
    "plan-eldritch-knight": Path("docs") / "plans" / "eldritch-knight.md",
    "plan-battle-master": Path("docs") / "plans" / "battle-master.md",
    "plan-paladin-oaths": Path("docs") / "plans" / "paladin-oaths.md",
    "plan-magic-items-automation": Path("docs") / "plans" / "magic-items-automation.md",
    "plan-exhaustion-levels": Path("docs") / "plans" / "exhaustion-levels.md",
    "plan-carrying-capacity": Path("docs") / "plans" / "carrying-capacity.md",
    "plan-legendary-actions": Path("docs") / "plans" / "legendary-actions.md",
    "plan-str-override": Path("docs") / "plans" / "str-override.md",
    "plan-charged-items": Path("docs") / "plans" / "charged-items.md",
    "plan-permanent-ability-increase-reconciliation": Path("docs") / "plans" / "permanent-ability-increase-reconciliation.md",
    "plan-race-features": Path("docs") / "plans" / "race-features.md",
    "plan-encounters": Path("docs") / "encounters-plan.md",
    "plan-multi-system-refactor": Path("docs") / "multi-system-refactor.md",
}


def _render_markdown_page(source: str, request: Request, fallback_title: str) -> HTMLResponse:
    """Render a markdown source string through the wiki_md.html
    template. Shared by the .md branch of ``/wiki/<slug>`` and the
    new ``/wiki/doc/<slug>`` route so both go through the same chrome
    (topnav + wiki nav menu + base.html footer).
    """
    rendered = md_lib.markdown(
        source,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    m = re.search(r"<h1[^>]*>(.*?)</h1>", rendered, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else fallback_title
    return templates.TemplateResponse("wiki_md.html", {
        "request": request,
        "title": title,
        "body": rendered,
    })


def _inject_wiki_nav(html: str, request: Request) -> str:
    """v2.49.9: inject the shared wiki nav menu after ``<body>`` on
    the standalone HTML guides under ``docs/wiki/<slug>.html`` so they
    pick up the same nav strip the Jinja-rendered pages get via
    ``{% include "_wiki_nav.html" %}``. Renders the partial through
    the templating engine so the same source is the single source of
    truth.

    The guides are designed to be self-contained for ``file://``
    preview, so we don't bake the nav into the file — the server
    injects it at request time.

    v2.49.11 fix: split on ``</head>`` first and only do the inject on
    the post-head half. A naive ``html.replace("<body>", …, 1)`` matches
    the FIRST occurrence of the literal string, which can land inside a
    CSS comment in the document's ``<style>`` block (e.g. "child of
    <body> (h1, p, …)"). Because ``_wiki_nav.html`` contains its own
    ``</style>`` tag, injecting it inside an outer ``<style>`` block
    closes that block prematurely and leaks all the trailing comment
    text into the visible body. Splitting on ``</head>`` guarantees we
    only ever match the real opening body tag.
    """
    nav_html = templates.get_template("_wiki_nav.html").render({"request": request})
    head, sep, rest = html.partition("</head>")
    if not sep:
        # Defensive — no </head> found; fall back to a broad match.
        return re.sub(r"(<body\b[^>]*>)", r"\1\n" + nav_html, html, count=1)
    rest = re.sub(r"(<body\b[^>]*>)", r"\1\n" + nav_html, rest, count=1)
    return head + sep + rest


@router.get("/wiki", response_class=HTMLResponse)
def wiki_home(request: Request):
    """Render the wiki landing page. Lists guides, plans, references,
    and repo-root docs, plus the TODO roadmap for guides yet to be
    written. Mirrors ``docs/wiki/README.md`` in content; the Jinja
    template extends the base shell so the topnav + footer + the
    v2.49.9 wiki nav menu appear consistently.
    """
    return templates.TemplateResponse("wiki.html", {"request": request})


@router.get("/wiki/doc/{slug}", response_class=HTMLResponse)
def wiki_doc(slug: str, request: Request):
    """v2.49.9: serve a plan / reference / repo-root markdown doc
    through the wiki chrome. Only slugs present in ``_DOC_ALLOWLIST``
    resolve — the allowlist guarantees we never traverse out of the
    repo regardless of the slug guard. Unknown slugs 404.
    """
    if not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail="Not found")
    rel_path = _DOC_ALLOWLIST.get(slug)
    if rel_path is None:
        raise HTTPException(status_code=404, detail="Not found")
    file_path = _REPO_ROOT / rel_path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    source = file_path.read_text(encoding="utf-8")
    return _render_markdown_page(source, request, fallback_title=slug)


@router.get("/wiki/{slug}", response_class=HTMLResponse)
def wiki_guide(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a self-contained HTML guide from ``docs/wiki/<slug>.html``
    or a markdown guide from ``docs/wiki/<slug>.md``.

    Slug is restricted to ``[a-zA-Z0-9_-]`` so we never traverse out of
    the wiki directory. Missing slugs return 404 (rather than serving
    the directory listing) so unknown paths don't fish for files.

    v2.43.4: the guide HTML inherits the user's theme. We look up the
    current user's ``theme`` preference (or fall back to the configured
    default), then string-substitute the ``<html lang="en">`` opener
    to add ``data-theme="<theme>"``. The guide's `<head>` already
    `<link>`s to /static/style.css, which carries the theme blocks for
    all 8 themes — the cascade picks the right one based on the
    injected attribute. File:// previews (no server) still work
    because the inline ``:root`` fallback in the guide stays in place
    as the dark-theme default.

    v2.49.9: the standalone HTML branch also gets the shared wiki nav
    menu injected after ``<body>`` so navigation between guides is
    consistent with the Jinja-rendered pages.
    """
    if not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail="Not found")

    # v2.43.14: try .md first (text-heavy guides like the broadcasts
    # catalog + endpoint catalog), then .html (visual guides like the
    # roll-log + toast guides).
    md_path = _WIKI_DIR / f"{slug}.md"
    html_path = _WIKI_DIR / f"{slug}.html"

    if md_path.is_file():
        source = md_path.read_text(encoding="utf-8")
        return _render_markdown_page(source, request, fallback_title=slug)

    if not html_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    user: Optional[User] = get_current_user(request, db)
    theme = (user.theme if user and user.theme else get_settings().default_theme) or "dark"
    # Read + inject theme. Keep the rewrite tiny: only the ``<html>``
    # opener changes. The guide's existing inline `<link>` to style.css
    # does the rest of the work via CSS cascade.
    html = html_path.read_text(encoding="utf-8")
    html = html.replace(
        '<html lang="en">',
        f'<html lang="en" data-theme="{theme}">',
        1,
    )
    # v2.49.9: inject the wiki nav menu after <body> so the standalone
    # guides share the same navigation as the Jinja-rendered pages.
    html = _inject_wiki_nav(html, request)
    return HTMLResponse(html)
