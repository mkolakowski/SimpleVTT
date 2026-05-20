"""In-repo wiki routes.

Serves the wiki landing page (``/wiki``) and the self-contained HTML
guides under ``docs/wiki/`` (``/wiki/<slug>``). Read-only, no auth — the
content is reference documentation, deliberately not gated. Lives in
its own router so the route list stays organized.

To add a new guide:
  1. Drop ``docs/wiki/<slug>.html`` into the repo (self-contained HTML).
  2. Add an entry in ``app/templates/wiki.html``'s "Available guides"
     table linking to ``/wiki/<slug>``.
  3. Add the same entry in ``docs/wiki/README.md`` so the on-disk index
     stays in sync.
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

_WIKI_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "wiki"


@router.get("/wiki", response_class=HTMLResponse)
def wiki_home(request: Request):
    """Render the wiki landing page. Lists the available guides + the
    TODO roadmap for guides yet to be written. Mirrors
    ``docs/wiki/README.md`` in content; the Jinja template extends the
    base shell so the topnav + footer (with the version + wiki link)
    appear consistently.
    """
    return templates.TemplateResponse("wiki.html", {"request": request})


@router.get("/wiki/{slug}", response_class=HTMLResponse)
def wiki_guide(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve a self-contained HTML guide from ``docs/wiki/<slug>.html``.

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
    """
    if not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail="Not found")

    # v2.43.14: try .md first (text-heavy guides like the broadcasts
    # catalog + endpoint catalog), then .html (visual guides like the
    # roll-log + toast guides). The .html branch keeps the v2.43.4
    # behavior — read the file, inject data-theme into the <html>
    # opener, return raw. The new .md branch renders through the
    # ``markdown`` package + wraps in the wiki_md.html template so
    # the same base.html chrome (topnav, footer, theme) wraps every
    # text guide consistently.
    md_path = _WIKI_DIR / f"{slug}.md"
    html_path = _WIKI_DIR / f"{slug}.html"

    if md_path.is_file():
        source = md_path.read_text(encoding="utf-8")
        rendered = md_lib.markdown(
            source,
            extensions=["tables", "fenced_code", "sane_lists"],
        )
        # Pull the first H1 as the page title, fall back to the slug.
        m = re.search(r"<h1[^>]*>(.*?)</h1>", rendered, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else slug
        return templates.TemplateResponse("wiki_md.html", {
            "request": request,
            "title": title,
            "body": rendered,
        })

    if not html_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    user: Optional[User] = get_current_user(request, db)
    theme = (user.theme if user and user.theme else get_settings().default_theme) or "dark"
    # Read + inject. Keep the rewrite tiny: only the ``<html>`` opener
    # changes. The guide's existing inline `<link>` to style.css does
    # the rest of the work via CSS cascade.
    html = html_path.read_text(encoding="utf-8")
    html = html.replace(
        '<html lang="en">',
        f'<html lang="en" data-theme="{theme}">',
        1,
    )
    return HTMLResponse(html)


