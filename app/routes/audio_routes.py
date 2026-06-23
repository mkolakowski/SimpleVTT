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
    in epoch milliseconds so clients can compute the seek offset.

    When audio is paused, ``paused`` is True and ``paused_offset_s`` carries
    the seek offset clients should park at. The WS reconnect sync in
    tabletop_routes.py uses this same payload so a player joining mid-pause
    lands at the correct position.
    """
    started_at = campaign.now_playing_started_at or datetime.utcnow()
    started_at_ms = int(started_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
    category = track.playlist.category if track.playlist else "music"
    paused = campaign.now_playing_paused_offset_s is not None
    return {
        "track_id": track.id,
        "playlist_id": track.playlist_id,
        "name": track.name,
        "file_url": track.file_url,
        "loop": campaign.now_playing_loop,
        "started_at_ms": started_at_ms,
        "category": category,
        "paused": paused,
        "paused_offset_s": float(campaign.now_playing_paused_offset_s) if paused else None,
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

def _normalize_playlist_tags(value) -> list[str]:
    """Coerce a tag input (list or comma-separated string) into a
    deduplicated list of trimmed short strings. Mirrors the helper in
    tabletop_routes._parse_tags so playlist tags stay consistent with
    encounter tags."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [t.strip() for t in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(t).strip() for t in value]
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in items:
        if not t:
            continue
        t = t[:40]
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= 20:
            break
    return out


@router.post("/campaign/{campaign_id}/playlists")
def create_playlist(
    campaign_id: int,
    name: str = Form(...),
    category: str = Form("music"),
    description: str = Form(""),
    tags: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _require_campaign_gm(db, user, campaign_id)
    cat = category if category in AUDIO_CATEGORIES else "music"
    pl = Playlist(
        campaign_id=campaign_id,
        name=name.strip()[:120] or "Untitled",
        category=cat,
        description=(description or "").strip()[:200],
        tags=_normalize_playlist_tags(tags),
    )
    db.add(pl)
    db.commit()
    return RedirectResponse(f"/campaign/{campaign_id}/settings#audio", status_code=303)


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/description")
async def set_playlist_description(
    campaign_id: int,
    playlist_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Set the playlist's short description (shown on the tabletop next
    to the name). Empty body clears it. GM-only."""
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    body = await request.json()
    pl.description = str(body.get("description") or "").strip()[:200]
    db.commit()
    return {"ok": True, "description": pl.description}


@router.post("/campaign/{campaign_id}/playlists/{playlist_id}/tags")
async def set_playlist_tags(
    campaign_id: int,
    playlist_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Replace the playlist's tag list. Body accepts either a JSON
    array or a comma-separated string. GM-only."""
    _require_campaign_gm(db, user, campaign_id)
    pl = (
        db.query(Playlist)
        .filter(Playlist.id == playlist_id, Playlist.campaign_id == campaign_id)
        .first()
    )
    if not pl:
        raise HTTPException(404, "Playlist not found")
    body = await request.json()
    pl.tags = _normalize_playlist_tags(body.get("tags"))
    db.commit()
    return {"ok": True, "tags": pl.tags}


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
        from ..storage_quota import check_quota
        _q = check_quota(db, campaign_id, len(data))
        if _q:
            raise HTTPException(413, _q)
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

def _finalize_play_event(db: Session, campaign_id: int, reason: str) -> None:
    """Close any in-flight ``AudioPlayEvent`` for the campaign with the
    given ``reason``. Idempotent — a no-op when nothing is ongoing. Does
    not commit; the caller commits alongside its own state changes.

    Computes ``duration_s`` as ``ended_at - started_at`` (clamped to 0).
    Multiple in-flight rows would be unusual (only happens if a previous
    play wasn't finalized — e.g. a crash mid-play); this iterates all
    of them to keep the table consistent.
    """
    from ..models import AudioPlayEvent
    now = datetime.utcnow()
    ongoing = (
        db.query(AudioPlayEvent)
        .filter(
            AudioPlayEvent.campaign_id == campaign_id,
            AudioPlayEvent.ended_at.is_(None),
        )
        .all()
    )
    for ev in ongoing:
        ev.ended_at = now
        ev.ended_reason = reason
        delta = (now - ev.started_at).total_seconds() if ev.started_at else 0
        ev.duration_s = max(0, int(delta))


def _open_play_event(
    db: Session,
    campaign_id: int,
    track: PlaylistTrack,
    source: str,
    user_id: "int | None",
) -> None:
    """Insert a new ``AudioPlayEvent`` for ``track`` with ``ended_at``
    NULL. Snapshots ``track.name`` and ``playlist.name`` so the row
    survives a later rename / delete of the source rows. Does not commit.
    """
    from ..models import AudioPlayEvent
    pl = track.playlist
    ev = AudioPlayEvent(
        campaign_id=campaign_id,
        track_id=track.id,
        playlist_id=track.playlist_id,
        track_name=(track.name or "")[:300],
        playlist_name=(pl.name if pl else "")[:200],
        started_at=datetime.utcnow(),
        ended_at=None,
        ended_reason="ongoing",
        source=source,
        triggered_by_user_id=user_id,
    )
    db.add(ev)


async def _start_track_for_campaign(
    db: Session,
    campaign: Campaign,
    track: PlaylistTrack,
    *,
    source: str = "manual",
    prev_reason: str = "skipped",
    user_id: "int | None" = None,
) -> None:
    """Set ``campaign.now_playing_*`` to ``track`` and broadcast audio_play.

    Caller is responsible for permission checks AND for ensuring the track
    belongs to the same campaign. Used by both the manual ``/audio/play``
    endpoint and the session-start auto-play hook in tabletop_routes.

    Audit fields (PR 4):
        ``source``      — how this play was triggered (manual / auto_start /
                          auto_next / loop). Stored on the new AudioPlayEvent.
        ``prev_reason`` — how to label the in-flight event being replaced
                          ("skipped" for GM jumps, "completed" for natural
                          end of file, "session_end" for cross-session
                          residue, etc.). See models.AudioPlayEvent docstring.
        ``user_id``     — who triggered the play, for the audit row's
                          ``triggered_by_user_id``.
    """
    _finalize_play_event(db, campaign.id, prev_reason)
    _open_play_event(db, campaign.id, track, source, user_id)
    campaign.now_playing_track_id = track.id
    # Record server-side start time so all clients can compute the same offset.
    campaign.now_playing_started_at = datetime.utcnow()
    # Starting a new track always clears any pause state from the previous one.
    campaign.now_playing_paused_offset_s = None
    db.commit()
    db.refresh(campaign)
    await hub.broadcast(
        campaign.id,
        {"type": "audio_play", "data": _now_playing_payload(campaign, track)},
    )


async def _stop_audio_for_campaign(
    db: Session, campaign: Campaign, *, reason: str = "stopped"
) -> None:
    """Clear ``campaign.now_playing_*`` and broadcast audio_stop.

    Used by both the manual ``/audio/stop`` endpoint and the session-end
    auto-stop hook. Idempotent — safe to call when nothing is playing.

    ``reason`` is the label stored on the in-flight AudioPlayEvent being
    finalized: ``"stopped"`` (GM hit stop), ``"session_end"`` (session
    ended), ``"completed"`` (playlist reached its natural end). Defaults
    to ``"stopped"`` since that's what the manual endpoint wants.
    """
    _finalize_play_event(db, campaign.id, reason)
    campaign.now_playing_track_id = None
    campaign.now_playing_started_at = None
    campaign.now_playing_paused_offset_s = None
    db.commit()
    await hub.broadcast(campaign.id, {"type": "audio_stop", "data": {}})


async def _pause_audio_for_campaign(db: Session, campaign: Campaign) -> None:
    """Pause whatever's currently playing for the campaign.

    Records the seek offset (server-side compute: ``now - started_at``)
    so resume can put everyone back in the same spot. Does NOT finalize
    the AudioPlayEvent — pause is "still listening, just not right now",
    not a play termination. Idempotent — already paused → no-op.
    """
    if campaign.now_playing_track_id is None:
        return  # Nothing to pause
    if campaign.now_playing_paused_offset_s is not None:
        return  # Already paused
    if campaign.now_playing_started_at is None:
        return
    offset = (datetime.utcnow() - campaign.now_playing_started_at).total_seconds()
    campaign.now_playing_paused_offset_s = max(0.0, offset)
    db.commit()
    await hub.broadcast(campaign.id, {
        "type": "audio_pause",
        "data": {"paused_offset_s": campaign.now_playing_paused_offset_s},
    })


async def _resume_audio_for_campaign(db: Session, campaign: Campaign) -> None:
    """Resume a paused campaign's audio.

    Sets ``now_playing_started_at = now - paused_offset_s`` so every
    client's existing time-sync math computes the same seek position,
    then clears the pause field and re-broadcasts ``audio_play`` with
    the fresh start timestamp. Idempotent — not paused → no-op.
    """
    if campaign.now_playing_track_id is None:
        return
    if campaign.now_playing_paused_offset_s is None:
        return
    track = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.id == campaign.now_playing_track_id)
        .first()
    )
    if not track:
        # Track was deleted while paused — clean up cleanly.
        await _stop_audio_for_campaign(db, campaign, reason="completed")
        return
    from datetime import timedelta
    offset = float(campaign.now_playing_paused_offset_s or 0.0)
    campaign.now_playing_started_at = datetime.utcnow() - timedelta(seconds=offset)
    campaign.now_playing_paused_offset_s = None
    db.commit()
    db.refresh(campaign)
    await hub.broadcast(
        campaign.id,
        {"type": "audio_play", "data": _now_playing_payload(campaign, track)},
    )


def _find_sibling_track(
    db: Session, current: PlaylistTrack, direction: int, *, loop: bool = False,
) -> Optional[PlaylistTrack]:
    """Return the previous (direction=-1) or next (direction=+1) track in
    the current track's playlist. With ``loop=True`` the search wraps
    around at the playlist boundary; otherwise returns None at the edge.
    """
    siblings = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == current.playlist_id)
        .order_by(PlaylistTrack.position, PlaylistTrack.id)
        .all()
    )
    if not siblings:
        return None
    try:
        idx = [t.id for t in siblings].index(current.id)
    except ValueError:
        return None
    target = idx + direction
    if 0 <= target < len(siblings):
        return siblings[target]
    if loop:
        return siblings[target % len(siblings)]
    return None


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
    # Manual GM jump → previous track (if any) is "skipped".
    await _start_track_for_campaign(
        db, campaign, track,
        source="manual", prev_reason="skipped", user_id=user.id,
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/stop")
async def stop_audio(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    campaign = _require_campaign_gm(db, user, campaign_id)
    await _stop_audio_for_campaign(db, campaign)
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
    finished_id are no-ops.

    Records the finished track as ``ended_reason='completed'`` (natural
    end of file) before opening the next event with source=``auto_next``
    or ``loop`` when the playlist loops back to the same/first track.
    """
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
        # Track was deleted while playing — finalize as completed and stop.
        await _stop_audio_for_campaign(db, campaign, reason="completed")
        return {"ok": True}
    next_track = _find_sibling_track(
        db, track, direction=+1, loop=campaign.now_playing_loop,
    )
    if next_track is None:
        # End of playlist + loop off — finalize as completed and stop.
        await _stop_audio_for_campaign(db, campaign, reason="completed")
        return {"ok": True}
    # Advance via the shared helper so the event audit is recorded the
    # same way as a manual play. ``prev_reason='completed'`` because the
    # finished track played to its natural end. ``source='loop'`` when
    # the playlist wraps back to the same single track playing again.
    src = "loop" if next_track.id == finished_id else "auto_next"
    await _start_track_for_campaign(
        db, campaign, next_track,
        source=src, prev_reason="completed", user_id=user.id,
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/skip")
async def skip_track(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only manual skip to the next track. Unlike ``/audio/next``
    (which is client-initiated when a track ends naturally), this is
    fired by the GM clicking ⏭. The current track is finalized as
    ``ended_reason='skipped'``.
    """
    campaign = _require_campaign_gm(db, user, campaign_id)
    if campaign.now_playing_track_id is None:
        return {"ok": True, "noop": True}
    track = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.id == campaign.now_playing_track_id)
        .first()
    )
    if not track:
        await _stop_audio_for_campaign(db, campaign, reason="completed")
        return {"ok": True}
    next_track = _find_sibling_track(
        db, track, direction=+1, loop=campaign.now_playing_loop,
    )
    if next_track is None:
        # End of playlist + loop off — skipping past the last track stops.
        await _stop_audio_for_campaign(db, campaign, reason="skipped")
        return {"ok": True}
    await _start_track_for_campaign(
        db, campaign, next_track,
        source="manual", prev_reason="skipped", user_id=user.id,
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/previous")
async def previous_track(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only jump back to the previous track in the current playlist.
    Wraps to the last track when loop is on and we're at track 1. The
    current track is finalized as ``ended_reason='skipped'``.
    """
    campaign = _require_campaign_gm(db, user, campaign_id)
    if campaign.now_playing_track_id is None:
        return {"ok": True, "noop": True}
    track = (
        db.query(PlaylistTrack)
        .filter(PlaylistTrack.id == campaign.now_playing_track_id)
        .first()
    )
    if not track:
        await _stop_audio_for_campaign(db, campaign, reason="completed")
        return {"ok": True}
    prev_track = _find_sibling_track(
        db, track, direction=-1, loop=campaign.now_playing_loop,
    )
    if prev_track is None:
        # At track 1 + loop off → no-op (no broadcast).
        return {"ok": True, "noop": True}
    await _start_track_for_campaign(
        db, campaign, prev_track,
        source="manual", prev_reason="skipped", user_id=user.id,
    )
    return {"ok": True}


@router.post("/campaign/{campaign_id}/audio/pause")
async def pause_audio(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only pause. Does not finalize the in-flight AudioPlayEvent —
    pause is mid-listen, not a play termination."""
    campaign = _require_campaign_gm(db, user, campaign_id)
    await _pause_audio_for_campaign(db, campaign)
    return {"ok": True, "paused_offset_s": campaign.now_playing_paused_offset_s}


@router.post("/campaign/{campaign_id}/audio/resume")
async def resume_audio(
    campaign_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """GM-only resume from pause. Re-broadcasts audio_play with an
    adjusted started_at so every client seeks to the same position."""
    campaign = _require_campaign_gm(db, user, campaign_id)
    await _resume_audio_for_campaign(db, campaign)
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
