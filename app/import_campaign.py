"""Campaign-clone import — re-place a ``simplevtt-export`` (level=campaign)
archive as a brand-new campaign.

Phase 6b of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). The mirror of
``app/export_campaign.py``: read the archive's data tree, extract its media
to fresh uuids (``import_bundle``), and re-create the FK-interconnected core
with **new** ids — remapping every cross-reference (a token's map / character
/ template, an encounter's map / playlist + its payload token refs, a track's
playlist) through old→new id maps built as each tier is created.

Scope: campaign, token_templates, maps, characters, tokens, playlists +
tracks, encounters (Phase 6b); handouts + non-encrypted notes (Phase 6c); the
embedded homebrew pack (Phase 6d, written after commit via the route's shared
``apply_homebrew_pack``). Only dice-roll history is intentionally not cloned
(low-value, user-FK ambiguity). The DB inserts are one transaction; on failure
the extracted media is unlinked so a failed import leaves nothing behind.
"""
from __future__ import annotations

import logging
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


def clone_campaign(
    db: Session,
    zf,
    manifest: dict,
    *,
    owner_user_id: int,
    uploads_root: Optional[Path] = None,
) -> dict:
    """Clone the archive into a new campaign owned by ``owner_user_id``.
    Returns ``{campaign_id, counts}``. Raises ``ib.BundleError`` on a
    malformed archive (the route maps that to 400)."""
    from .models import (
        Campaign, CampaignNote, Character, Encounter, GridType, Handout, Map,
        Playlist, PlaylistTrack, Token, TokenTemplate,
    )

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
        counts: dict[str, int] = {}

        # Token templates (no inbound FK except tokens, created next).
        tpl_map: dict = {}
        templates = ib.rewrite_urls(
            ib.read_json(zf, "data/token_templates.json"), url_map,
        ) if _has(zf, "data/token_templates.json") else []
        for t in templates:
            nt = TokenTemplate(
                campaign_id=nc, name=(t.get("name") or "NPC")[:200],
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
                campaign_id=nc, owner_user_id=owner_user_id,
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
                campaign_id=nc, name=(m.get("name") or "Map")[:120],
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

        # Tokens — remap map / character / template; drop a token whose map
        # didn't come across.
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
                campaign_id=nc, name=(p.get("name") or "Playlist")[:120],
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
                campaign_id=nc, name=(e.get("name") or "Encounter")[:160],
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
        # (revealed=False default) so the importing GM re-prepares reveals;
        # authored by the importer.
        handouts = ib.rewrite_urls(
            ib.read_json(zf, "data/handouts.json"), url_map,
        ) if _has(zf, "data/handouts.json") else []
        for h in handouts:
            if not isinstance(h, dict):
                continue
            db.add(Handout(
                campaign_id=nc, author_user_id=owner_user_id,
                title=(h.get("title") or "Handout")[:200], body=h.get("body") or "",
                image_url=h.get("image_url"), folder=h.get("folder") or "",
                revealed=False,
            ))
        counts["handouts"] = len(handouts)

        # Notes — only NON-encrypted notes clone (per-campaign E2E keys don't
        # round-trip, so encrypted private notes are skipped). Authored by the
        # importer.
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
                campaign_id=nc, author_user_id=owner_user_id,
                kind=n.get("kind") or "gm_note",
                visibility=n.get("visibility") or "gm_only",
                title=n.get("title"), body=n.get("body") or "",
                folder=n.get("folder") or "", pinned=bool(n.get("pinned", False)),
            ))
            note_n += 1
        counts["notes"] = note_n
        counts["notes_skipped_encrypted"] = note_skipped

        db.commit()
    except Exception:
        db.rollback()
        ib.cleanup_extracted(url_map, uploads_root=uploads_root)
        raise

    # Homebrew pack — written to the filesystem AFTER the DB commit (mirrors
    # reset_and_reseed), reusing the route's apply logic via a lazy import to
    # avoid an import cycle. Isolated in its own try so a homebrew hiccup never
    # triggers the media-cleanup path above (the rows are already committed).
    counts["homebrew_created"] = 0
    try:
        if _has(zf, "data/homebrew.json"):
            pack = ib.read_json(zf, "data/homebrew.json")
            if isinstance(pack, dict):
                from .routes.tabletop_routes import apply_homebrew_pack
                hb = apply_homebrew_pack(nc, pack, owner_user_id=owner_user_id)
                counts["homebrew_created"] = hb.get("totals", {}).get("created", 0)
    except Exception:
        log.exception("clone campaign %s: homebrew apply failed", nc)

    return {"campaign_id": nc, "counts": counts}
