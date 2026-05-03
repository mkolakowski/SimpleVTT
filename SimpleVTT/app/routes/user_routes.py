"""User-facing settings page.

For now this hosts per-track audio volume overrides. Profile/password
management could be layered on later.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import (
    Campaign,
    CampaignMembership,
    Playlist,
    PlaylistTrack,
    User,
    UserAudioPreference,
)
from ..templates import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def user_settings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Show all per-track volume overrides for this user, grouped by
    campaign + playlist. Tracks the user has set an override for are
    listed first; the rest are listed under each playlist for easy
    discovery so they can preset overrides before a session."""
    # Build the set of campaigns this user can see (primary GM + co-GM + member).
    visible_ids = set()
    visible_ids.update(
        c.id for c in db.query(Campaign).filter(Campaign.gm_user_id == user.id).all()
    )
    visible_ids.update(
        m.campaign_id
        for m in db.query(CampaignMembership)
        .filter(CampaignMembership.user_id == user.id)
        .all()
    )
    if user.is_admin:
        visible_ids.update(c.id for c in db.query(Campaign).all())

    # Existing overrides as {track_id: volume}
    overrides = {
        p.track_id: p.volume
        for p in db.query(UserAudioPreference)
        .filter(UserAudioPreference.user_id == user.id)
        .all()
    }

    # Group tracks by campaign -> playlist for display.
    grouped = []  # list of {campaign, playlists: [{playlist, tracks: [...]}]}
    if visible_ids:
        campaigns = (
            db.query(Campaign).filter(Campaign.id.in_(visible_ids)).order_by(Campaign.name).all()
        )
        for c in campaigns:
            playlists = (
                db.query(Playlist)
                .filter(Playlist.campaign_id == c.id)
                .order_by(Playlist.name)
                .all()
            )
            pls = []
            for pl in playlists:
                tracks = (
                    db.query(PlaylistTrack)
                    .filter(PlaylistTrack.playlist_id == pl.id)
                    .order_by(PlaylistTrack.position, PlaylistTrack.id)
                    .all()
                )
                track_rows = [
                    {"track": t, "volume": overrides.get(t.id)} for t in tracks
                ]
                if track_rows:
                    pls.append({"playlist": pl, "tracks": track_rows})
            if pls:
                grouped.append({"campaign": c, "playlists": pls})

    overrides_count = len(overrides)
    return templates.TemplateResponse(
        "user_settings.html",
        {
            "request": request,
            "user": user,
            "grouped": grouped,
            "overrides_count": overrides_count,
        },
    )
