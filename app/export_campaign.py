"""Campaign-level ``simplevtt-export`` assembly + background build.

Phase 4 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). Walks a campaign's full child
tree into the archive layout the Phase 2 primitives (``app/export_bundle.py``)
define, bundles the referenced media, and writes the zip to a staging path.
``run_campaign_export_job`` is the background-task entry point: it opens its
own DB session (the request's is closed once the POST responds) and drives the
``app/export_jobs.py`` registry so the client's poll sees live progress.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from . import export_jobs
from .export_bundle import (
    abs_path_for_url,
    archive_path_for,
    build_manifest,
    bundle_to_bytes,
    find_media_urls,
    row_to_dict,
    write_bundle_zip,
)

log = logging.getLogger(__name__)


def staging_dir() -> Path:
    """Where in-progress/finished export zips are staged. Overridable so an
    operator can point it at a roomier volume than the default tmp dir."""
    d = Path(os.environ.get("EXPORT_STAGING_DIR", "/tmp/simplevtt-exports"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _homebrew_pack(campaign_id: int, campaign_name: str, exported_at: str) -> dict:
    """Rebuild the ``simplevtt-homebrew`` pack for the campaign (the same shape
    ``/homebrew/export`` produces) so the archive's homebrew round-trips through
    the existing ``/homebrew/import``. Reuses the per-type projection registry
    from the routes module via a lazy import (the routes module is already
    loaded at app start; the lazy import just avoids an import cycle)."""
    from . import local_content
    from .routes.tabletop_routes import _HOMEBREW_ITEM_EXPORT, HOMEBREW_EXPORT_VERSION

    pack: dict = {
        "format": "simplevtt-homebrew",
        "version": HOMEBREW_EXPORT_VERSION,
        "campaign": campaign_name,
        "exported_at": exported_at,
    }
    for ctype, (key, projector) in _HOMEBREW_ITEM_EXPORT.items():
        rows = local_content.search(type=ctype, campaign_id=campaign_id, limit=500)[0]
        pack[key] = [projector(r) for r in rows if r.get("_source") == "local-homebrew"]
    return pack


def build_campaign_bundle(
    db: Session,
    campaign,
    *,
    app_version: str,
    schema_version: int,
    exported_at: str,
    staging: Path,
    job_id: Optional[str] = None,
) -> tuple[Path, dict]:
    """Assemble ``campaign`` into a ``simplevtt-export`` zip under ``staging``.
    Returns ``(zip_path, counts)``. Updates the job's progress/stage if a
    ``job_id`` is given."""
    from .models import (
        Character, DiceRoll, Encounter, Handout, Map,
        CampaignNote, Playlist, PlaylistTrack, Token, TokenTemplate,
    )

    cid = campaign.id

    def _p(pct: int, stage: str) -> None:
        if job_id:
            export_jobs.update(job_id, progress=pct, stage=stage)

    _p(5, "campaign")
    data_files: dict[str, object] = {"data/campaign.json": row_to_dict(campaign)}

    _p(15, "characters")
    chars = db.query(Character).filter(Character.campaign_id == cid).all()
    for c in chars:
        data_files[f"data/characters/{c.id}.json"] = row_to_dict(c)

    _p(30, "maps")
    maps = db.query(Map).filter(Map.campaign_id == cid).all()
    for m in maps:
        data_files[f"data/maps/{m.id}.json"] = row_to_dict(m)
    map_ids = [m.id for m in maps]
    tokens = (
        db.query(Token).filter(Token.map_id.in_(map_ids)).all() if map_ids else []
    )
    data_files["data/tokens.json"] = [row_to_dict(t) for t in tokens]

    templates = db.query(TokenTemplate).filter(TokenTemplate.campaign_id == cid).all()
    data_files["data/token_templates.json"] = [row_to_dict(t) for t in templates]

    _p(45, "encounters")
    encounters = db.query(Encounter).filter(Encounter.campaign_id == cid).all()
    for e in encounters:
        data_files[f"data/encounters/{e.id}.json"] = row_to_dict(e)

    playlists = db.query(Playlist).filter(Playlist.campaign_id == cid).all()
    pl_ids = [p.id for p in playlists]
    tracks = (
        db.query(PlaylistTrack).filter(PlaylistTrack.playlist_id.in_(pl_ids)).all()
        if pl_ids else []
    )
    data_files["data/playlists.json"] = {
        "playlists": [row_to_dict(p) for p in playlists],
        "tracks": [row_to_dict(t) for t in tracks],
    }

    notes = db.query(CampaignNote).filter(CampaignNote.campaign_id == cid).all()
    data_files["data/notes.json"] = [row_to_dict(n) for n in notes]

    handouts = db.query(Handout).filter(Handout.campaign_id == cid).all()
    data_files["data/handouts.json"] = [row_to_dict(h) for h in handouts]

    rolls = db.query(DiceRoll).filter(DiceRoll.campaign_id == cid).all()
    data_files["data/dice_rolls.json"] = [row_to_dict(r) for r in rolls]

    _p(60, "homebrew")
    data_files["data/homebrew.json"] = _homebrew_pack(cid, campaign.name, exported_at)

    counts = {
        "characters": len(chars), "maps": len(maps), "tokens": len(tokens),
        "token_templates": len(templates), "encounters": len(encounters),
        "playlists": len(playlists), "playlist_tracks": len(tracks),
        "notes": len(notes), "handouts": len(handouts), "dice_rolls": len(rolls),
    }

    _p(75, "media")
    media_files: list[tuple[str, Path]] = []
    media_manifest: list[dict] = []
    for url in find_media_urls(data_files):
        arc = archive_path_for(url)
        src = abs_path_for_url(url)
        if src is None:
            continue
        media_files.append((arc, src))
        media_manifest.append({"archive_path": arc, "original_url": url})

    _p(90, "zipping")
    manifest = build_manifest(
        "campaign",
        app_version=app_version,
        schema_version=schema_version,
        exported_at=exported_at,
        source_campaign_id=cid,
        source_campaign_name=campaign.name,
        counts=counts,
        media_manifest=media_manifest,
    )
    zip_path = staging / f"campaign-{cid}-{job_id or 'sync'}.zip"
    write_bundle_zip(zip_path, manifest=manifest, data_files=data_files, media_files=media_files)
    return zip_path, counts


def build_character_bundle_bytes(
    db: Session,
    character,
    *,
    app_version: str,
    schema_version: int,
    exported_at: str,
) -> tuple[bytes, str]:
    """Assemble a single character into an in-memory ``simplevtt-export`` zip
    (level=character) and return ``(zip_bytes, filename)``.

    Character-scoped only: the character row (sheet JSON carries stats +
    notes + portrait ref), that character's own dice rolls, and the
    portrait/sheet media — never any campaign-wide data. Small enough to
    build synchronously, so no job/staging-file lifecycle."""
    from .models import Campaign, DiceRoll

    data_files: dict[str, object] = {"data/character.json": row_to_dict(character)}
    rolls = db.query(DiceRoll).filter(DiceRoll.character_id == character.id).all()
    data_files["data/dice_rolls.json"] = [row_to_dict(r) for r in rolls]

    campaign_name = None
    if character.campaign_id is not None:
        camp = db.get(Campaign, character.campaign_id)
        campaign_name = camp.name if camp else None

    media_files: list[tuple[str, Path]] = []
    media_manifest: list[dict] = []
    for url in find_media_urls(data_files):
        arc = archive_path_for(url)
        src = abs_path_for_url(url)
        if src is None:
            continue
        media_files.append((arc, src))
        media_manifest.append({"archive_path": arc, "original_url": url})

    manifest = build_manifest(
        "character",
        app_version=app_version,
        schema_version=schema_version,
        exported_at=exported_at,
        source_campaign_id=character.campaign_id,
        source_campaign_name=campaign_name,
        counts={"dice_rolls": len(rolls)},
        media_manifest=media_manifest,
    )
    data = bundle_to_bytes(manifest=manifest, data_files=data_files, media_files=media_files)
    filename = f"simplevtt-character-{character.id}-{exported_at[:10]}.zip"
    return data, filename


def run_campaign_export_job(
    job_id: str,
    campaign_id: int,
    *,
    app_version: str,
    schema_version: int,
    exported_at: str,
) -> None:
    """Background-task entry point: build the campaign zip in its own DB
    session and mark the job done/errored. Never raises (a failure is
    reported through the job registry, not the response)."""
    from .database import SessionLocal
    from .models import Campaign

    db = SessionLocal()
    try:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None:
            export_jobs.fail(job_id, error="Campaign not found.")
            return
        zip_path, _counts = build_campaign_bundle(
            db, campaign,
            app_version=app_version,
            schema_version=schema_version,
            exported_at=exported_at,
            staging=staging_dir(),
            job_id=job_id,
        )
        filename = f"simplevtt-campaign-{campaign_id}-{exported_at[:10]}.zip"
        export_jobs.finish(job_id, zip_path=str(zip_path), filename=filename)
    except Exception as e:  # noqa: BLE001 — report via the job, never crash the worker
        log.exception("campaign export job %s failed", job_id)
        export_jobs.fail(job_id, error=str(e))
    finally:
        db.close()
