"""Per-campaign audio playlists.

GMs upload tracks (mp3/ogg/wav/m4a) into named playlists, then start playback.
The currently-playing track + its server-side start timestamp are persisted
on Campaign so reconnecting clients sync to the right position.

Player-side:
  - Master volume + mute live in localStorage (handled in audio.js).
  - Per-track volume overrides live server-side in user_audio_preferences,
    so they follow the user across browsers/devices.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import (
    AUDIO_CATEGORIES,
    Campaign,
    Playlist,
    PlaylistTrack,
    User,
    UserAudioCategoryPref,
    UserAudioPreference,
)
from ..realtime import hub
from .tabletop_routes import _user_can_view_campaign, _user_is_gm

router = APIRouter()
log = logging.getLogger(__name__)


def _extract_audio_metadata(data: bytes, filename: str) -> dict:
    """Return {track_artist, track_album, track_genre, track_year} from audio bytes.
    Uses format-specific easy-tag interfaces so key names are always normalised.
    All values are str or None. Logs a warning if mutagen is unavailable."""
    import io
    ext = Path(filename).suffix.lower()
    fileobj = io.BytesIO(data)
    audio = None
    try:
        if ext == ".mp3":
            from mutagen.mp3 import EasyMP3
            audio = EasyMP3(fileobj)
        elif ext in (".m4a", ".aac", ".mp4"):
            from mutagen.mp4 import EasyMP4
            audio = EasyMP4(fileobj)
        elif ext in (".ogg", ".oga"):
            from mutagen.oggvorbis import OggVorbis
            audio = OggVorbis(fileobj)
        elif ext == ".flac":
            from mutagen.flac import FLAC
            audio = FLAC(fileobj)
        elif ext == ".wav":
            from mutagen.wave import WAVE
            audio = WAVE(fileobj)
        else:
            from mutagen import File as MutagenFile
            audio = MutagenFile(fileobj, filename=filename, easy=True)
    except ImportError:
        log.warning("mutagen is not installed — audio metadata will not be extracted. "
                    "Run: pip install mutagen")
        return {}
    except Exception as exc:
        log.warning("metadata extraction failed for %s: %s", filename, exc)
        return {}

    if audio is None or audio.tags is None:
        return {}

    tags = audio.tags

    def _first(*keys: str) -> str | None:
        for k in keys:
            try:
                v = tags.get(k)
                if v is None and hasattr(tags, "__getitem__"):
                    try:
                        v = tags[k]
                    except KeyError:
                        pass
                if v:
                    s = str(v[0]) if isinstance(v, (list, tuple)) else str(v)
                    s = s.strip()
                    if s:
                        return s
            except Exception:
                pass
        return None

    year_raw = _first("date", "year", "originaldate")
    year = year_raw[:4] if year_raw and year_raw[:4].isdigit() else None
    return {
        "track_artist": _first("artist", "albumartist"),
        "track_album":  _first("album"),
        "track_genre":  _first("genre"),
        "track_year":   year,
    }


UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "static" / "uploads"
AUDIO_DIR = UPLOAD_ROOT / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/x-m4a", "audio/aac",
}
MAX_AUDIO_BYTES = 30 * 1024 * 1024


def _require_campaign_gm(db: Session, user: User, campaign_id: int) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_is_gm(user, campaign, db):
        raise HTTPException(403, "GM only")
    return campaign


def _now_playing_payload(campaign: Campaign, track: PlaylistTrack) -> dict:
    """Build the audio_play broadcast payload, including the start timestamp
    in epoch milliseconds so clients can compute the seek offset."""
    started_at = campaign.now_playing_started_at or datetime.utcnow()
    started_at_ms = int(started_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
    category = track.playlist.category if track.playlist else "music"
    return {
        "track_id": track.id,
        "playlist_id": track.playlist_id,
        "name": track.name,
        "file_url": track.file_url,
        "loop": campaign.now_playing_loop,
        "started_at_ms": started_at_ms,
        "category": category,
    }


# ---------- metadata backfill ----------

@router.post("/campaign/{campaign_id}/audio/backfill_metadata")
def backfill_metadata(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-extract and persist ID3/Vorbis metadata for every track whose audio
    file is still on disk. Safe to call multiple times."""
    _require_campaign_gm(db, user, campaign_id)
    static_root = Path(__file__).resolve().parent.parent / "static"
    playlists = db.query(Playlist).filter(Playlist.campaign_id == campaign_id).all()
    updated = 0
    for pl in playlists:
        for track in pl.tracks:
            rel = track.file_url.lstrip("/")
            fpath = static_root / rel.removeprefix("static/")
            if not fpath.exists():
                continue
            meta = _extract_audio_metadata(fpath.read_bytes(), fpath.name)
            if not meta:
                continue
            for k, v in meta.items():
                setattr(track, k, v)
            updated += 1
    db.commit()
    return {"ok": True, "updated": updated}


# ---------- playlist CRUD ----------

@router.post("/campaign/{campaign_id}/playlists")
def create_playlist(
    campaign_id: int,
    name: str = Form(...),
    category: str = Form("music"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    cat = category if category in AUDIO_CATEGORIES else "music"
    pl = Playlist(campaign_id=campaign_id, name=name.strip()[:120] or "Untitled", category=cat)
    db.add(pl)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/rename")
async def rename_playlist(
    campaign_id: int,
    playlist_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    body = await request.json()
    name = (body.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    pl.name = name
    db.commit()
    return {"ok": True, "name": pl.name}


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/category")
async def set_playlist_category(
    campaign_id: int,
    playlist_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    body = await request.json()
    cat = str(body.get("category", "music")).lower()
    if cat not in AUDIO_CATEGORIES:
        raise HTTPException(400, f"category must be one of: {', '.join(AUDIO_CATEGORIES)}")
    pl.category = cat
    db.commit()
    return {"ok": True, "category": pl.category}


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/delete")
async def delete_playlist(
    campaign_id: int,
    playlist_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    track_ids = [t.id for t in pl.tracks]
    if campaign.now_playing_track_id in track_ids:
        campaign.now_playing_track_id = None
        campaign.now_playing_started_at = None
        await hub.broadcast(campaign_id, {"type": "audio_stop", "data": {}})
    db.delete(pl)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/tracks")
async def upload_track(
    campaign_id: int,
    playlist_id: int,
    audio: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    last = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position.desc())
        .first()
    )
    next_pos = (last.position + 1) if last else 0
    for file in audio:
        if not file.filename:
            continue
        if file.content_type not in ALLOWED_AUDIO_TYPES:
            ext_ok = file.filename.lower().endswith((".mp3", ".ogg", ".oga", ".wav", ".m4a", ".aac"))
            if not ext_ok:
                raise HTTPException(400, f"Unsupported audio type: {file.content_type}")
        data = await file.read()
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(400, f"{file.filename} exceeds 30 MB limit")
        ext = Path(file.filename).suffix.lower() or ".mp3"
        fname = f"{uuid.uuid4().hex}{ext}"
        (AUDIO_DIR / fname).write_bytes(data)
        meta = _extract_audio_metadata(data, file.filename)
        db.add(PlaylistTrack(
            playlist_id=playlist_id,
            name=Path(file.filename).stem[:200] or "Untitled",
            file_url=f"/static/uploads/audio/{fname}",
            position=next_pos,
            **meta,
        ))
        next_pos += 1
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


@router.post("/campaign/{campaign_id}/tracks/{track_id}/rename")
async def rename_track(
    campaign_id: int,
    track_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    track = (
        db.query(PlaylistTrack)
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .filter(PlaylistTrack.id == track_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not track:
        raise HTTPException(404, "Track not found")
    body = await request.json()
    name = (body.get("name") or "").strip()[:200]
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    track.name = name
    db.commit()
    return {"ok": True, "name": track.name}


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/reorder")
async def reorder_tracks(
    campaign_id: int,
    playlist_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    body = await request.json()
    order = body.get("order", [])
    track_map = {t.id: t for t in pl.tracks}
    for pos, tid in enumerate(order):
        if tid in track_map:
            track_map[tid].position = pos
    db.commit()
    return {"ok": True}


@router.post("/campaign/{campaign_id}/tracks/{track_id}/delete")
async def delete_track(
    campaign_id: int,
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _require_campaign_gm(db, user, campaign_id)
    track = (
        db.query(PlaylistTrack)
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .filter(PlaylistTrack.id == track_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not track:
        raise HTTPException(404, "Track not found")
    if campaign.now_playing_track_id == track.id:
        campaign.now_playing_track_id = None
        campaign.now_playing_started_at = None
        await hub.broadcast(campaign_id, {"type": "audio_stop", "data": {}})
    try:
        rel = track.file_url.replace("/static/", "", 1)
        f = Path(__file__).resolve().parent.parent / "static" / rel
        if f.exists():
            f.unlink()
    except Exception as e:
        log.warning("could not delete %s: %s", track.file_url, e)
    db.delete(track)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


# ---------- playback control ----------

@router.post("/campaign/{campaign_id}/audio/play")
async def play_track(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    body = await request.json()
    track_id = int(body.get("track_id"))
    campaign = _require_campaign_gm(db, user, campaign_id)
    track = (
        db.query(PlaylistTrack)
        .join(Playlist, Playlist.id == PlaylistTrack.playlist_id)
        .filter(PlaylistTrack.id == track_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not track:
        raise HTTPException(404, "Track not found")
    campaign.now_playing_track_id = track.id
    # Record server-side start time so all clients can compute the same offset.
    campaign.now_playing_started_at = datetime.utcnow()
    db.commit()
    db.refresh(campaign)
    await hub.broadcast(
        campaign_id,
        {"type": "audio_play", "data": _now_playing_payload(campaign, track)},
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/stop")
async def stop_audio(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _require_campaign_gm(db, user, campaign_id)
    campaign.now_playing_track_id = None
    campaign.now_playing_started_at = None
    db.commit()
    await hub.broadcast(campaign_id, {"type": "audio_stop", "data": {}})
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/next")
async def next_in_playlist(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Called by client when a track ends naturally. Advances to the next
    track. The first client to send wins; subsequent calls for the same
    finished_id are no-ops."""
    body = await request.json()
    finished_id = int(body.get("track_id"))
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if campaign.now_playing_track_id != finished_id:
        return {"ok": True, "noop": True}
    track = db.query(PlaylistTrack).filter(PlaylistTrack.id == finished_id).first()
    if not track:
        campaign.now_playing_track_id = None
        campaign.now_playing_started_at = None
        db.commit()
        await hub.broadcast(campaign_id, {"type": "audio_stop", "data": {}})
        return {"ok": True}
    siblings = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == track.playlist_id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
        .all()
    )
    ids = [t.id for t in siblings]
    try:
        idx = ids.index(track.id)
    except ValueError:
        idx = -1
    next_track: Optional[PlaylistTrack] = None
    if idx >= 0 and idx + 1 < len(siblings):
        next_track = siblings[idx + 1]
    elif campaign.now_playing_loop and siblings:
        next_track = siblings[0]
    if next_track is None:
        campaign.now_playing_track_id = None
        campaign.now_playing_started_at = None
        db.commit()
        await hub.broadcast(campaign_id, {"type": "audio_stop", "data": {}})
        return {"ok": True}
    campaign.now_playing_track_id = next_track.id
    campaign.now_playing_started_at = datetime.utcnow()
    db.commit()
    db.refresh(campaign)
    await hub.broadcast(
        campaign_id,
        {"type": "audio_play", "data": _now_playing_payload(campaign, next_track)},
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/loop")
def set_loop(
    campaign_id: int,
    loop: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _require_campaign_gm(db, user, campaign_id)
    campaign.now_playing_loop = bool(loop)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


@router.post("/campaign/{campaign_id}/audio/resync")
async def resync_audio(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-broadcast the current audio_play state. Useful for clients that
    drifted out of sync — any user in the campaign can request it."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign or not _user_can_view_campaign(db, user, campaign):
        raise HTTPException(403, "Not a member")
    if not campaign.now_playing_track_id:
        return {"ok": True, "playing": False}
    track = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.id == campaign.now_playing_track_id)
        .first()
    )
    if not track:
        return {"ok": True, "playing": False}
    await hub.broadcast(
        campaign_id,
        {"type": "audio_play", "data": _now_playing_payload(campaign, track)},
    )
    return {"ok": True, "playing": True}


# ---------- per-user per-category volume preferences ----------

@router.get("/api/audio/category-preferences")
def get_category_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return all per-category volume overrides for the current user.
    Returns {music: 0.8, sfx: 0.6, environment: 0.7} — missing keys mean 1.0.
    audio.js fetches this on connect."""
    rows = (
        db.query(UserAudioCategoryPref)
        .filter(UserAudioCategoryPref.user_id == user.id)
        .all()
    )
    return {r.category: r.volume for r in rows}


@router.post("/api/audio/category-preferences/{category}")
async def set_category_preference(
    category: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set a per-category volume for the current user.
    Body: {"volume": 0.0..1.0}
    """
    if category not in AUDIO_CATEGORIES:
        raise HTTPException(400, f"category must be one of: {', '.join(AUDIO_CATEGORIES)}")
    body = await request.json()
    try:
        vol = float(body.get("volume", 1.0))
    except (TypeError, ValueError):
        raise HTTPException(400, "volume must be a number 0.0-1.0")
    if not 0.0 <= vol <= 1.0:
        raise HTTPException(400, "volume must be between 0.0 and 1.0")
    pref = (
        db.query(UserAudioCategoryPref)
        .filter(
            UserAudioCategoryPref.user_id == user.id,
            UserAudioCategoryPref.category == category,
        )
        .first()
    )
    if pref:
        pref.volume = vol
    else:
        db.add(UserAudioCategoryPref(user_id=user.id, category=category, volume=vol))
    db.commit()
    return {"ok": True, "category": category, "volume": vol}
