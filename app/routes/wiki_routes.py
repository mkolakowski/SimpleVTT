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

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

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
def wiki_guide(slug: str):
    """Serve a self-contained HTML guide from ``docs/wiki/<slug>.html``.

    Slug is restricted to ``[a-zA-Z0-9_-]`` so we never traverse out of
    the wiki directory. Missing slugs return 404 (rather than serving
    the directory listing) so unknown paths don't fish for files.
    """
    if not slug.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=404, detail="Not found")
    path = _WIKI_DIR / f"{slug}.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="text/html")
