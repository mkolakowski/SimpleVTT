"""Authorization gate for uploaded media under ``/static/uploads/``.

v2.1047.0. The generalization of ``serve_handout_media`` (v2.1046.0) to
the rest of the uploads tree: map images, campaign/map thumbnails, token
art, character portraits, token-template art, encounter backgrounds, and
audio tracks. Until now every one of those was served by the ``/static``
mount with **no auth check** — unguessable-UUID capability URLs. Anyone
holding the URL, logged in or not, got the bytes, so a GM's unrevealed
map was one leaked link away from being public.

**Why the URL shape is unchanged.** ``/app/app/static/uploads`` is the
``uploads_data`` named volume: files moved off it stop being backed up
and vanish on the next container rebuild. The admin center's storage
accounting also walks that volume and indexes by *basename* taken from
the DB URL columns, so rewriting the columns to a private scheme would
silently drop media out of per-campaign quota enforcement. Intercepting
the route instead keeps backups, storage accounting, the schema, the
export/import bundles, and every client untouched — and retroactively
protects media that already exists.

**Resolution is by exact URL match across every column that can hold
one.** Not per-bucket: a file under ``maps/`` may be referenced by
``Campaign.thumbnail_url`` rather than ``Map.image_url`` (the v2.1043.0
"reuse a map image as the campaign thumbnail" feature), so a
bucket-keyed lookup would wrongly deny it. The column set mirrors
``admin_center/storage.py::_build_index``, which is the established
inventory of "every DB column that holds an uploads URL."

**Orphans fail closed.** A file referenced by no row (left behind when
its row was deleted — the app has never deleted media on row delete)
returns 404. Nothing in the UI links to an unreferenced file, so this
breaks no rendering; it just means a stale URL stops working. The
regression risk of this design is *missing* a column, which
``tests/harness/test_media_gate.py`` guards by harvesting the media URLs
the real settings page renders and asserting each one still serves.

**Caching.** Unlike handout media (``no-store``, because a revoked
reveal must take effect immediately), ordinary campaign art is
revalidated rather than re-downloaded: ``private, max-age=0,
must-revalidate`` keeps shared/proxy caches out while letting the
browser hold bytes and confirm them with a conditional request. This
handler answers ``If-None-Match`` with a 304 itself, because
``FileResponse`` — unlike ``StaticFiles`` — does not.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Campaign,
    Character,
    Encounter,
    Handout,
    Map,
    Playlist,
    PlaylistTrack,
    Token,
    TokenTemplate,
    User,
)
from .tabletop_routes import _user_can_view_campaign

_UPLOADS_ROOT = (
    Path(__file__).resolve().parent.parent / "static" / "uploads"
)
_UPLOADS_URL_PREFIX = "/static/uploads/"

# Buckets this gate owns. ``handouts`` is deliberately absent — it has
# its own stricter handler (``notes_routes.serve_handout_media``,
# per-player reveal rules + no-store) registered ahead of this one.
_GATED_BUCKETS = {
    "maps",
    "thumbnails",
    "tokens",
    "portraits",
    "token_templates",
    "encounter_bg",
    "audio",
}

# Ordinary campaign art: let the browser cache bytes but force a
# conditional check, and keep shared caches out entirely.
_CACHE_CONTROL = "private, max-age=0, must-revalidate"

# NOTE: deliberately NOT memoized. An earlier revision cached
# url → owner for 300 s and it broke revocation: deleting a map left its
# file readable until the entry aged out, which contradicts the whole
# point of resolving by DB reference. Repeat traffic is cheap anyway —
# the browser revalidates with If-None-Match and gets a 304 (see
# ``serve_upload``), and the lookups below are exact-equality matches on
# small tables. Add invalidation hooks before adding a cache back.


def resolve_media_owner(db: Session, url: str) -> "tuple[str, int] | None":
    """Who owns the uploaded file at ``url``?

    Returns ``("campaign", campaign_id)``, ``("user", user_id)`` for a
    standalone character's portrait, or ``None`` when no row references
    it. Mirrors ``admin_center/storage.py::_build_index``'s column set —
    if a column is added there, add it here too.
    """
    def _campaign(cid):
        return ("campaign", cid) if cid is not None else None

    # Campaign-level art.
    c = (
        db.query(Campaign)
        .filter((Campaign.thumbnail_url == url)
                | (Campaign.active_background_url == url)
                | (Campaign.default_background_url == url))
        .first()
    )
    found = _campaign(c.id) if c else None

    if not found:
        m = (
            db.query(Map)
            .filter((Map.image_url == url) | (Map.thumbnail_url == url))
            .first()
        )
        found = _campaign(m.campaign_id) if m else None

    if not found:
        t = db.query(Token).filter(Token.image_url == url).first()
        if t is not None:
            owning_map = db.query(Map).filter(Map.id == t.map_id).first()
            found = _campaign(owning_map.campaign_id) if owning_map else None

    if not found:
        tt = (
            db.query(TokenTemplate)
            .filter(TokenTemplate.image_url == url)
            .first()
        )
        found = _campaign(tt.campaign_id) if tt else None

    if not found:
        e = db.query(Encounter).filter(Encounter.background_url == url).first()
        found = _campaign(e.campaign_id) if e else None

    if not found:
        h = (
            db.query(Handout)
            .filter((Handout.image_url == url) | (Handout.file_url == url))
            .first()
        )
        found = _campaign(h.campaign_id) if h else None

    if not found:
        tr = (
            db.query(PlaylistTrack)
            .filter(PlaylistTrack.file_url == url)
            .first()
        )
        if tr is not None:
            pl = (
                db.query(Playlist)
                .filter(Playlist.id == tr.playlist_id)
                .first()
            )
            found = _campaign(pl.campaign_id) if pl else None

    if not found:
        # Portraits last: a standalone character (campaign_id NULL, e.g.
        # one detached by settings_delete_character) keeps its portrait,
        # and is owned by a *user* rather than a campaign.
        ch = (
            db.query(Character)
            .filter(Character.portrait_url == url)
            .first()
        )
        if ch is not None:
            found = (
                _campaign(ch.campaign_id)
                if ch.campaign_id is not None
                else ("user", ch.owner_user_id)
            )

    return found


def _may_read(db: Session, user: User, owner: "tuple[str, int]") -> bool:
    kind, owner_id = owner
    if kind == "campaign":
        campaign = db.query(Campaign).filter(Campaign.id == owner_id).first()
        return bool(campaign) and _user_can_view_campaign(db, user, campaign)
    if kind == "user":
        # A standalone character's portrait: its owner, or an admin
        # (who can already administer that character).
        return user.id == owner_id or bool(user.is_admin)
    return False


async def serve_upload(
    bucket: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve an uploaded file, gated on the requester's access to the
    campaign (or user) that owns it. Registered directly on the app
    ahead of the ``/static`` mount — see ``app/main.py``.

    Every failure is a flat 404 rather than 401/403: a 403 would confirm
    that a given campaign's map exists, which is the thing an
    unauthorized caller must not learn.
    """
    not_found = HTTPException(404, "Not found")
    if bucket not in _GATED_BUCKETS:
        raise not_found
    # Registered with a ``:path`` converter so a nested path can't slip
    # past this handler to the static mount; separators and traversal
    # segments are rejected here rather than resolved.
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise not_found
    if filename in ("", ".", ".."):
        raise not_found

    path = _UPLOADS_ROOT / bucket / filename
    if not path.is_file():
        raise not_found

    user = get_current_user(request, db)
    if not user:
        raise not_found

    url = f"{_UPLOADS_URL_PREFIX}{bucket}/{filename}"
    owner = resolve_media_owner(db, url)
    if owner is None or not _may_read(db, user, owner):
        raise not_found

    # ``stat_result`` must be passed for FileResponse to stamp
    # ETag/Last-Modified at construction — without it they're only set
    # when the response is sent, so the conditional check below would
    # never see an ETag to compare against.
    response = FileResponse(
        path,
        headers={"Cache-Control": _CACHE_CONTROL},
        stat_result=path.stat(),
    )
    # FileResponse stamps an ETag but, unlike StaticFiles, never answers
    # a conditional request — without this every revalidation would ship
    # the whole file again.
    etag = response.headers.get("etag")
    if etag and request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": _CACHE_CONTROL},
        )
    return response
