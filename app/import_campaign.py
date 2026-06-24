"""Campaign import — re-place a ``simplevtt-export`` (level=campaign) archive.

Phase 6b–6d + 7 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). The mirror of
``app/export_campaign.py``: read the archive's data tree, extract its media to
fresh uuids (``import_bundle``), and re-create the FK-interconnected core with
**new** ids — remapping every cross-reference (a token's map / character /
template, an encounter's map / playlist + its payload token refs, a track's
playlist) through old→new id maps built as each tier is created.

Two modes share one populate engine (``_populate_campaign``):

  - **clone** — create a brand-new campaign owned by the importer and populate
    it (homebrew add-only into the fresh scope).
  - **restore** — wipe an existing campaign's content in place
    (``wipe_campaign_children``, keeping the campaign row + memberships) and
    repopulate it from the archive (homebrew scope cleared then re-written).

Scope: campaign, token_templates, maps, characters, tokens, playlists +
tracks, encounters, handouts, non-encrypted notes, and the homebrew pack.
Only dice-roll history is intentionally not re-placed. The DB inserts are one
transaction; on failure the extracted media is unlinked so a failed import
leaves nothing behind. Homebrew is written after commit (mirrors
reset_and_reseed) and isolated so a hiccup can't trigger media cleanup for
already-committed rows.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from . import import_bundle as ib

log = logging.getLogger(__name__)


def _int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _read_dir(zf, prefix: str) -> list:
    """Read every ``<prefix>*.json`` entry (e.g. ``data/characters/``)."""
    out = []
    for name in zf.namelist():
        if name.startswith(prefix) and name.endswith(".json"):
            out.append(ib.read_json(zf, name))
    return out


def _has(zf, name: str) -> bool:
    return name in set(zf.namelist())


def _remap_payload(payload: dict, char_map: dict, tpl_map: dict) -> dict:
    """Best-effort remap of an encounter payload's per-token ``character_id``
    / ``template_id`` refs through the old→new id maps. Unmapped refs become
    None so a stale id never points at an unrelated row in the new campaign."""
    if not isinstance(payload, dict):
        return {}
    out = dict(payload)
    toks = out.get("tokens")
    if isinstance(toks, list):
        new_toks = []
        for t in toks:
            if not isinstance(t, dict):
                continue
            t = dict(t)
            if "character_id" in t:
                t["character_id"] = char_map.get(t.get("character_id"))
            if "template_id" in t:
                t["template_id"] = tpl_map.get(t.get("template_id"))
            new_toks.append(t)
        out["tokens"] = new_toks
    return out


def _populate_campaign(db: Session, zf, url_map: dict, *, campaign_id: int, owner_user_id: int) -> dict:
    """Create the archive's child tree into ``campaign_id`` (which must already
    exist), remapping FKs to fresh ids. Returns per-table counts. Does not
    commit — the caller owns the transaction. Shared by clone + restore."""
    from .models import (
        CampaignNote, Character, Encounter, GridType, Handout, Map,
        Playlist, PlaylistTrack, Token, TokenTemplate,
    )

    counts: dict[str, int] = {}

    # Token templates (no inbound FK except tokens, created next).
    tpl_map: dict = {}
    templates = ib.rewrite_urls(
        ib.read_json(zf, "data/token_templates.json"), url_map,
    ) if _has(zf, "data/token_templates.json") else []
    for t in templates:
        nt = TokenTemplate(
            campaign_id=campaign_id, name=(t.get("name") or "NPC")[:200],
            image_url=t.get("image_url"), tags=t.get("tags") or [],
            template=t.get("template") or "generic", sheet=t.get("sheet") or {},
        )
        db.add(nt)
        db.flush()
        if t.get("id") is not None:
            tpl_map[t["id"]] = nt.id
    counts["token_templates"] = len(templates)

    # Characters (owned by the importer).
    char_map: dict = {}
    chars = _read_dir(zf, "data/characters/")
    for c in chars:
        c = ib.rewrite_urls(c, url_map)
        ch = Character(
            campaign_id=campaign_id, owner_user_id=owner_user_id,
            name=(c.get("name") or "Character")[:120],
            template=c.get("template") or "generic", sheet=c.get("sheet") or {},
            portrait_url=c.get("portrait_url"), color=c.get("color"),
            ring_style=c.get("ring_style"),
        )
        db.add(ch)
        db.flush()
        if c.get("id") is not None:
            char_map[c["id"]] = ch.id
    counts["characters"] = len(chars)

    # Maps.
    map_map: dict = {}
    maps = _read_dir(zf, "data/maps/")
    for m in maps:
        m = ib.rewrite_urls(m, url_map)
        try:
            gt = GridType(m.get("grid_type"))
        except (ValueError, KeyError):
            gt = GridType.SQUARE
        nm = Map(
            campaign_id=campaign_id, name=(m.get("name") or "Map")[:120],
            image_url=m.get("image_url"), grid_type=gt,
            grid_size_px=_int(m.get("grid_size_px"), 70),
            grid_offset_x=_int(m.get("grid_offset_x"), 0),
            grid_offset_y=_int(m.get("grid_offset_y"), 0),
            show_grid=bool(m.get("show_grid", True)),
            width_px=_int(m.get("width_px"), 2000),
            height_px=_int(m.get("height_px"), 1500),
            tags=m.get("tags") or [], folder=m.get("folder") or "",
            thumbnail_url=m.get("thumbnail_url"),
            player_spawns=m.get("player_spawns") or {},
        )
        db.add(nm)
        db.flush()
        if m.get("id") is not None:
            map_map[m["id"]] = nm.id
    counts["maps"] = len(maps)

    # Tokens — remap map / character / template; drop a token whose map didn't
    # come across.
    tokens = ib.rewrite_urls(
        ib.read_json(zf, "data/tokens.json"), url_map,
    ) if _has(zf, "data/tokens.json") else []
    tok_n = 0
    for t in tokens:
        new_map = map_map.get(t.get("map_id"))
        if new_map is None:
            continue
        db.add(Token(
            map_id=new_map,
            character_id=char_map.get(t.get("character_id")),
            controller_user_id=None,
            token_template_id=tpl_map.get(t.get("token_template_id")),
            label=t.get("label") or "", color=t.get("color") or "#cc3333",
            image_url=t.get("image_url"), x=_float(t.get("x"), 0),
            y=_float(t.get("y"), 0), size=_int(t.get("size"), 1),
            is_hidden=bool(t.get("is_hidden", False)),
            hidden_from_user_ids=[], team=t.get("team") or "neutral",
            disguise=t.get("disguise"),
        ))
        tok_n += 1
    counts["tokens"] = tok_n

    # Playlists + tracks.
    pl_map: dict = {}
    pdata = ib.rewrite_urls(
        ib.read_json(zf, "data/playlists.json"), url_map,
    ) if _has(zf, "data/playlists.json") else {"playlists": [], "tracks": []}
    playlists = pdata.get("playlists") or []
    for p in playlists:
        np = Playlist(
            campaign_id=campaign_id, name=(p.get("name") or "Playlist")[:120],
            description=p.get("description") or "", tags=p.get("tags") or [],
            category=p.get("category") or "music",
        )
        db.add(np)
        db.flush()
        if p.get("id") is not None:
            pl_map[p["id"]] = np.id
    trk_n = 0
    for tr in (pdata.get("tracks") or []):
        new_pl = pl_map.get(tr.get("playlist_id"))
        if new_pl is None:
            continue
        db.add(PlaylistTrack(
            playlist_id=new_pl, name=(tr.get("name") or "Track")[:200],
            file_url=tr.get("file_url") or "", position=_int(tr.get("position"), 0),
            track_artist=tr.get("track_artist"), track_album=tr.get("track_album"),
            track_genre=tr.get("track_genre"), track_year=tr.get("track_year"),
        ))
        trk_n += 1
    counts["playlists"] = len(playlists)
    counts["playlist_tracks"] = trk_n

    # Encounters — remap map + playlist + payload token refs.
    encs = _read_dir(zf, "data/encounters/")
    for e in encs:
        e = ib.rewrite_urls(e, url_map)
        db.add(Encounter(
            campaign_id=campaign_id, name=(e.get("name") or "Encounter")[:160],
            description=e.get("description") or "",
            map_id=map_map.get(e.get("map_id")),
            background_url=e.get("background_url"),
            auto_play_playlist_id=pl_map.get(e.get("auto_play_playlist_id")),
            auto_play_mode=e.get("auto_play_mode") or "order",
            auto_play_track_id=None,  # track id remap omitted; plays in order
            payload=_remap_payload(e.get("payload") or {}, char_map, tpl_map),
            tags=e.get("tags") or [],
            use_spawn_points=bool(e.get("use_spawn_points", False)),
            spawn_points=e.get("spawn_points") or {},
            folder=e.get("folder") or "",
            stop_audio_on_load=bool(e.get("stop_audio_on_load", False)),
        ))
    counts["encounters"] = len(encs)

    # Handouts — GM-authored, never encrypted. Re-created unrevealed
    # (revealed=False) so the importing GM re-prepares reveals; authored by
    # the importer.
    handouts = ib.rewrite_urls(
        ib.read_json(zf, "data/handouts.json"), url_map,
    ) if _has(zf, "data/handouts.json") else []
    for h in handouts:
        if not isinstance(h, dict):
            continue
        db.add(Handout(
            campaign_id=campaign_id, author_user_id=owner_user_id,
            title=(h.get("title") or "Handout")[:200], body=h.get("body") or "",
            image_url=h.get("image_url"), folder=h.get("folder") or "",
            revealed=False,
        ))
    counts["handouts"] = len(handouts)

    # Notes — only NON-encrypted notes (per-campaign E2E keys don't round-trip,
    # so encrypted private notes are skipped). Authored by the importer.
    notes = ib.read_json(zf, "data/notes.json") if _has(zf, "data/notes.json") else []
    note_n = 0
    note_skipped = 0
    for n in notes:
        if not isinstance(n, dict):
            continue
        if n.get("is_encrypted"):
            note_skipped += 1
            continue
        db.add(CampaignNote(
            campaign_id=campaign_id, author_user_id=owner_user_id,
            kind=n.get("kind") or "gm_note",
            visibility=n.get("visibility") or "gm_only",
            title=n.get("title"), body=n.get("body") or "",
            folder=n.get("folder") or "", pinned=bool(n.get("pinned", False)),
        ))
        note_n += 1
    counts["notes"] = note_n
    counts["notes_skipped_encrypted"] = note_skipped

    return counts


def _clear_homebrew_scope(campaign_id: int) -> None:
    """Remove a campaign's homebrew scope dir (restore replaces it)."""
    try:
        from .local_content import HOMEBREW_ROOT
        scope = HOMEBREW_ROOT / "dnd5e" / f"campaign-{campaign_id}"
        if scope.is_dir():
            shutil.rmtree(scope)
    except OSError as e:
        log.warning("restore: failed to clear homebrew scope for %s: %s", campaign_id, e)


def _apply_homebrew_after_commit(zf, campaign_id: int, owner_user_id: int) -> int:
    """Write the archive's embedded homebrew pack into the campaign's scope,
    AFTER the DB commit (mirrors reset_and_reseed), reusing the route's apply
    logic via a lazy import. Isolated so a hiccup never propagates. Returns the
    created count."""
    try:
        if _has(zf, "data/homebrew.json"):
            pack = ib.read_json(zf, "data/homebrew.json")
            if isinstance(pack, dict):
                from .routes.tabletop_routes import apply_homebrew_pack
                hb = apply_homebrew_pack(campaign_id, pack, owner_user_id=owner_user_id)
                return hb.get("totals", {}).get("created", 0)
    except Exception:
        log.exception("import campaign %s: homebrew apply failed", campaign_id)
    return 0


def clone_campaign(
    db: Session,
    zf,
    manifest: dict,
    *,
    owner_user_id: int,
    uploads_root: Optional[Path] = None,
) -> dict:
    """Clone the archive into a NEW campaign owned by ``owner_user_id``.
    Returns ``{campaign_id, counts}``."""
    from .models import Campaign

    url_map = ib.extract_media(zf, manifest, uploads_root=uploads_root)
    try:
        camp_data = ib.rewrite_urls(ib.read_json(zf, "data/campaign.json"), url_map)
        if not isinstance(camp_data, dict):
            raise ib.BundleError("data/campaign.json is not an object.")
        new_camp = Campaign(
            name=(camp_data.get("name") or "Imported Campaign")[:120],
            description=camp_data.get("description") or "",
            game_system=camp_data.get("game_system") or "dnd5e",
            gm_user_id=owner_user_id,
            thumbnail_url=camp_data.get("thumbnail_url"),
        )
        db.add(new_camp)
        db.flush()
        nc = new_camp.id
        counts = _populate_campaign(db, zf, url_map, campaign_id=nc, owner_user_id=owner_user_id)
        db.commit()
    except Exception:
        db.rollback()
        ib.cleanup_extracted(url_map, uploads_root=uploads_root)
        raise

    counts["homebrew_created"] = _apply_homebrew_after_commit(zf, nc, owner_user_id)
    return {"campaign_id": nc, "counts": counts}


def restore_campaign(
    db: Session,
    zf,
    manifest: dict,
    *,
    target_campaign_id: int,
    owner_user_id: int,
    uploads_root: Optional[Path] = None,
) -> dict:
    """Restore the archive INTO an existing campaign, replacing its content in
    place: wipe the child tree (keeping the campaign row + memberships) then
    repopulate from the archive. Returns ``{campaign_id, counts}``. The caller
    must have already authorized GM access to ``target_campaign_id``."""
    from .campaign_wipe import wipe_campaign_children

    url_map = ib.extract_media(zf, manifest, uploads_root=uploads_root)
    try:
        # Replace content, keep the people: memberships survive a restore.
        wipe_campaign_children(db, [target_campaign_id], delete_memberships=False)
        counts = _populate_campaign(
            db, zf, url_map, campaign_id=target_campaign_id, owner_user_id=owner_user_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        ib.cleanup_extracted(url_map, uploads_root=uploads_root)
        raise

    # Replace homebrew too: clear the scope then re-write from the archive.
    _clear_homebrew_scope(target_campaign_id)
    counts["homebrew_created"] = _apply_homebrew_after_commit(zf, target_campaign_id, owner_user_id)
    return {"campaign_id": target_campaign_id, "counts": counts}
