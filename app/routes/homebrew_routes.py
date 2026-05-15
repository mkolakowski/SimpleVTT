"""Homebrew authoring + import routes.

All endpoints write to the file-based homebrew volume via
``app.local_content.write_homebrew`` (validated by per-type Pydantic models)
or delete files via ``delete_homebrew``. No DB rows are involved.

Routes
------
    GET  /admin/homebrew                              — list page
    POST /admin/homebrew/<type>/new                   — create from form
    POST /admin/homebrew/<type>/<slug>/edit           — update existing
    POST /admin/homebrew/<type>/<slug>/delete         — delete
    POST /admin/homebrew/<type>/import/open5e/<slug>  — copy one Open5e record
                                                       into the homebrew volume
    POST /admin/homebrew/<type>/import/upload         — accept arbitrary JSON
                                                       (paste or file)

Scope handling
--------------
Every write endpoint accepts ``scope`` as a form field. Values:

* ``"global"`` (default) — visible in every campaign in the system.
* ``"campaign-<N>"`` — only that campaign sees the record.

Path-traversal protection lives in ``local_content._safe_*`` helpers; this
module only forwards user input to them and surfaces the resulting
``ValueError`` as HTTP 400.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from ..auth import require_admin
from ..content_schemas import TYPE_REGISTRY
from ..local_content import write_homebrew, delete_homebrew, resolve, search
from ..models import User
from ..templates import templates

router = APIRouter()


# ── Read-only public lookup ──────────────────────────────────────────────────
# Lets the character sheet client fetch a content record by (type, slug) so it
# can render the record's `actions` array via window.renderActionButtons.
# Not under /admin because players need read access to their own race / class
# / feat / item actions.

@router.get("/api/content/{type}/{slug}")
def content_lookup(type: str, slug: str, campaign_id: int | None = None):
    _require_known_type(type)
    hit = resolve(slug, type=type, campaign_id=campaign_id)
    if not hit:
        raise HTTPException(404, f"no {type}/{slug} in homebrew or shipped SRD")
    record, source = hit
    return {"source": source, "record": record}
log = logging.getLogger(__name__)

_OPEN5E_BASE = "https://api.open5e.com/v1"

# Maps our internal content_type directory to the Open5e v1 endpoint slug.
# Items have three upstream endpoints — the import-by-slug helper picks one
# based on the slug prefix (e.g. ``magicitems/<slug>``).
_OPEN5E_ENDPOINTS = {
    "spells": "spells",
    "monsters": "monsters",
    "feats": "feats",
    "backgrounds": "backgrounds",
    "conditions": "conditions",
    "class_features": "classes",
    "subclass_features": "subclasses",
    "races": "races",
    # ``items`` is a synthetic SimpleVTT type that aggregates three upstream
    # endpoints. The caller picks via the form field ``open5e_endpoint``
    # (``magicitems`` | ``weapons`` | ``armor``); see ``import_open5e``.
}


def _require_known_type(type: str) -> str:
    if type not in TYPE_REGISTRY:
        raise HTTPException(404, f"Unknown content type: {type!r}")
    return type


@router.get("/admin/homebrew", response_class=HTMLResponse)
def homebrew_list(
    request: Request,
    type: str = "spells",
    scope: str = "global",
    campaign_id: int | None = None,
    user: User = Depends(require_admin),
):
    """Render the list page for one content type + scope. The template uses
    type tabs and a scope selector; the page initialises to ``type``."""
    _require_known_type(type)
    if scope.startswith("campaign-") and campaign_id is None:
        try:
            campaign_id = int(scope.split("-", 1)[1])
        except (ValueError, IndexError):
            campaign_id = None
    records, total = search(
        type=type,
        campaign_id=campaign_id,
        limit=200,
    )
    return templates.TemplateResponse(
        request,
        "admin/homebrew/list.html",
        {
            "request": request,
            "user": user,
            "type": type,
            "type_choices": list(TYPE_REGISTRY.keys()),
            "scope": scope,
            "records": records,
            "total": total,
        },
    )


@router.post("/admin/homebrew/{type}/new")
async def homebrew_create(
    request: Request,
    type: str,
    user: User = Depends(require_admin),
):
    """Form POST → validate → atomic file write. Body field ``payload`` carries
    the JSON-serialised record (matches the Action editor's hidden input)."""
    _require_known_type(type)
    form = await request.form()
    raw = form.get("payload")
    if not raw:
        raise HTTPException(400, "missing payload")
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"payload is not valid JSON: {e}")

    scope = form.get("scope") or "global"
    record.setdefault("scope", scope)
    record.setdefault("source", "homebrew")
    record.setdefault("owner", user.id)

    try:
        final = write_homebrew(record, type=type, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log.info("homebrew create: %s by user %s", final, user.id)
    return RedirectResponse(
        url=f"/admin/homebrew?type={type}&scope={scope}",
        status_code=303,
    )


@router.post("/admin/homebrew/{type}/{slug}/edit")
async def homebrew_edit(
    request: Request,
    type: str,
    slug: str,
    user: User = Depends(require_admin),
):
    """Idempotent rewrite. Same payload shape as ``new``. The slug in the URL
    must match the slug in the payload; otherwise 400."""
    _require_known_type(type)
    form = await request.form()
    raw = form.get("payload")
    if not raw:
        raise HTTPException(400, "missing payload")
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"payload is not valid JSON: {e}")

    if (record.get("slug") or "").lower() != slug.lower():
        raise HTTPException(400, "slug in URL does not match slug in payload")

    scope = form.get("scope") or record.get("scope") or "global"
    record["scope"] = scope
    record.setdefault("source", "homebrew")
    record.setdefault("owner", user.id)

    try:
        final = write_homebrew(record, type=type, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log.info("homebrew edit: %s by user %s", final, user.id)
    return RedirectResponse(
        url=f"/admin/homebrew?type={type}&scope={scope}",
        status_code=303,
    )


@router.post("/admin/homebrew/{type}/{slug}/delete")
async def homebrew_delete(
    request: Request,
    type: str,
    slug: str,
    user: User = Depends(require_admin),
):
    _require_known_type(type)
    form = await request.form()
    scope = form.get("scope") or "global"
    try:
        removed = delete_homebrew(slug, type=type, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not removed:
        raise HTTPException(404, f"no homebrew file at {scope}/{type}/{slug}.json")
    log.info("homebrew delete: %s/%s/%s by user %s", scope, type, slug, user.id)
    return RedirectResponse(
        url=f"/admin/homebrew?type={type}&scope={scope}",
        status_code=303,
    )


@router.post("/admin/homebrew/{type}/import/open5e/{slug}")
def import_open5e(
    request: Request,
    type: str,
    slug: str,
    user: User = Depends(require_admin),
    scope: str = Form("global"),
    open5e_endpoint: str | None = Form(None),
):
    """Fetch one record from the Open5e v1 API and save it as a homebrew file.

    Useful for pulling non-SRD content the GM has license to use (Tasha's
    options, third-party CC-licensed content, etc.) into their campaign
    without re-authoring it.
    """
    _require_known_type(type)
    endpoint = open5e_endpoint or _OPEN5E_ENDPOINTS.get(type)
    if not endpoint:
        raise HTTPException(
            400,
            f"specify ?open5e_endpoint= for content type {type!r} "
            f"(items maps to magicitems | weapons | armor)",
        )
    url = f"{_OPEN5E_BASE}/{endpoint}/{slug}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SimpleVTT/2.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            upstream = json.loads(r.read())
    except Exception as exc:
        raise HTTPException(502, f"Open5e fetch failed: {exc}")

    # Light passthrough: trust the Open5e fields and let the Pydantic model
    # ignore anything it doesn't understand (model_config extra='allow').
    # Heavier per-type transformation lives in scripts/build_srd_content.py
    # for bulk SRD imports; this single-record path stays minimal so anything
    # Pydantic accepts gets through.
    record = dict(upstream)
    record["scope"] = scope
    record["source"] = "homebrew"
    record["owner"] = user.id
    record.setdefault("_attribution", f"Imported from Open5e endpoint {endpoint}/{slug} via admin")

    try:
        final = write_homebrew(record, type=type, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log.info("homebrew import open5e: %s by user %s", final, user.id)
    return JSONResponse({"ok": True, "path": str(final), "slug": record.get("slug")})


@router.post("/admin/homebrew/{type}/import/upload")
async def import_upload(
    request: Request,
    type: str,
    user: User = Depends(require_admin),
):
    """Accept a pasted or uploaded JSON blob and save it as a homebrew file.

    Form fields: ``payload`` (JSON string) OR ``file`` (uploaded .json), plus
    ``scope``. Pydantic validation runs in ``write_homebrew``; failures raise
    HTTP 400 with the validation error message.
    """
    _require_known_type(type)
    form = await request.form()
    scope = form.get("scope") or "global"
    raw = form.get("payload")
    upload = form.get("file")
    if not raw and isinstance(upload, UploadFile):
        raw = (await upload.read()).decode("utf-8")
    if not raw:
        raise HTTPException(400, "provide either payload= or file=")

    try:
        record = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"payload is not valid JSON: {e}")

    if not isinstance(record, dict):
        raise HTTPException(400, "payload must be a JSON object, not an array")

    record["scope"] = scope
    record["source"] = "homebrew"
    record["owner"] = user.id

    try:
        final = write_homebrew(record, type=type, scope=scope)
    except ValueError as e:
        raise HTTPException(400, str(e))
    log.info("homebrew import upload: %s by user %s", final, user.id)
    return JSONResponse({"ok": True, "path": str(final), "slug": record.get("slug")})
