"""Storage accounting for the admin center.

A read-only, on-demand roll-up of how many **bytes** of uploaded files
SimpleVTT holds — the filesystem-side companion to ``inventory.py``'s row
counts. Per Arc B1 of ``docs/plans/app-wide-roles-and-storage.md``.

Attribution model: every uploaded file under ``/static/uploads/<subdir>/``
is referenced by a DB URL column tied (directly or transitively) to a
``campaign_id`` → ``Campaign.gm_user_id``. So each file is attributed to its
**campaign**, and the campaign to its **GM user**. Standalone character
portraits (a character with no campaign) attribute to the character's
**owner** directly. Files referenced by no DB row → an "unattributed"
bucket. Usage is computed by an on-demand filesystem walk (no per-file DB
size tracking).

DB/ORM imports are lazy (inside the functions) so importing this module on a
host without a database — as the unit tests do for the pure aggregator —
never triggers engine creation.
"""
from __future__ import annotations

import os
from pathlib import Path

# Upload subdir → display "type". The walk derives the type from the subdir
# so it's decoupled from which DB column referenced the file.
_TYPE_BY_SUBDIR = {
    "maps": "maps",
    "thumbnails": "thumbnails",
    "tokens": "tokens",
    "portraits": "portraits",
    "token_templates": "token_templates",
    "encounter_bg": "backgrounds",
    "handouts": "handouts",
    "audio": "audio",
}


def _uploads_root() -> Path:
    """Same in-image path the app mounts the uploads volume at (and the
    Center now shares RW)."""
    return Path(__file__).resolve().parent.parent / "static" / "uploads"


def _basename(url) -> str:
    return os.path.basename((url or "").strip()) if url else ""


def aggregate(uploads_root: Path, index: dict, campaign_meta: dict, user_email: dict) -> dict:
    """Pure aggregator (no DB): walk ``uploads_root`` and attribute each
    file's bytes via ``index`` (basename → {campaign_id, user_id}).

    - ``campaign_meta``: campaign_id → {"name", "gm_user_id"}.
    - ``user_email``: user_id → email.

    Returns the structured storage report. Testable on a tmp tree with a
    hand-built index.
    """
    uploads_root = Path(uploads_root)
    total_bytes = total_files = 0
    by_type: dict[str, int] = {}
    unattributed_bytes = unattributed_files = 0
    # campaign_id → {"bytes", "files", "by_type": {}}
    camp: dict = {}
    # user_id → {"bytes", "files", "by_type": {}, "campaigns": set(), "standalone_bytes"}
    usr: dict = {}

    def _user(uid):
        return usr.setdefault(uid, {"bytes": 0, "files": 0, "by_type": {}, "campaigns": set(), "standalone_bytes": 0})

    if uploads_root.is_dir():
        for sub in sorted(p for p in uploads_root.iterdir() if p.is_dir()):
            ftype = _TYPE_BY_SUBDIR.get(sub.name, sub.name)
            for f in sub.rglob("*"):
                if not f.is_file():
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                total_bytes += size
                total_files += 1
                by_type[ftype] = by_type.get(ftype, 0) + size
                entry = index.get(f.name)
                if entry and entry.get("campaign_id") is not None:
                    cid = entry["campaign_id"]
                    c = camp.setdefault(cid, {"bytes": 0, "files": 0, "by_type": {}})
                    c["bytes"] += size
                    c["files"] += 1
                    c["by_type"][ftype] = c["by_type"].get(ftype, 0) + size
                    gm = (campaign_meta.get(cid) or {}).get("gm_user_id")
                    if gm is not None:
                        u = _user(gm)
                        u["bytes"] += size
                        u["files"] += 1
                        u["by_type"][ftype] = u["by_type"].get(ftype, 0) + size
                        u["campaigns"].add(cid)
                elif entry and entry.get("user_id") is not None:
                    uid = entry["user_id"]
                    u = _user(uid)
                    u["bytes"] += size
                    u["files"] += 1
                    u["by_type"][ftype] = u["by_type"].get(ftype, 0) + size
                    u["standalone_bytes"] += size
                else:
                    unattributed_bytes += size
                    unattributed_files += 1

    # Shape the per-campaign list (newest/biggest first).
    by_campaign = []
    for cid, c in camp.items():
        meta = campaign_meta.get(cid) or {}
        gm = meta.get("gm_user_id")
        by_campaign.append({
            "campaign_id": cid,
            "name": meta.get("name", f"<campaign {cid}>"),
            "gm_email": user_email.get(gm, f"<user {gm}>") if gm is not None else "—",
            "bytes": c["bytes"],
            "files": c["files"],
            "by_type": c["by_type"],
        })
    by_campaign.sort(key=lambda r: r["bytes"], reverse=True)

    # Shape the per-user list, with each user's per-campaign breakdown.
    by_user = []
    for uid, u in usr.items():
        camps = [r for r in by_campaign if (campaign_meta.get(r["campaign_id"]) or {}).get("gm_user_id") == uid]
        by_user.append({
            "user_id": uid,
            "email": user_email.get(uid, f"<user {uid}>"),
            "bytes": u["bytes"],
            "files": u["files"],
            "by_type": u["by_type"],
            "standalone_bytes": u["standalone_bytes"],
            "by_campaign": camps,
        })
    by_user.sort(key=lambda r: r["bytes"], reverse=True)

    return {
        "available": True,
        "totals": {"bytes": total_bytes, "files": total_files},
        "by_type": by_type,
        "by_user": by_user,
        "by_campaign": by_campaign,
        "unattributed": {"bytes": unattributed_bytes, "files": unattributed_files},
    }


def _build_index(db):
    """Build basename→{campaign_id|user_id} from every DB URL column, plus
    campaign_meta + user_email lookups. (Imports models lazily via caller.)"""
    from ..models import (
        Campaign,
        Character,
        Encounter,
        Handout,
        Map,
        PlaylistTrack,
        Playlist,
        Token,
        TokenTemplate,
        User,
    )

    # NOTE (v2.1047.0): this column set is mirrored by
    # ``app/routes/media_routes.py::resolve_media_owner``, which decides
    # who may *read* each uploaded file. A column added here without
    # being added there makes its media 404 for everyone; a column added
    # there without being added here makes its bytes escape per-campaign
    # quota accounting. Keep the two in step.
    index: dict[str, dict] = {}

    def _add(url, *, campaign_id=None, user_id=None):
        bn = _basename(url)
        if bn:
            index[bn] = {"campaign_id": campaign_id, "user_id": user_id}

    # Campaign-level files.
    for c in db.query(Campaign).all():
        _add(c.thumbnail_url, campaign_id=c.id)
        _add(getattr(c, "active_background_url", None), campaign_id=c.id)
        _add(getattr(c, "default_background_url", None), campaign_id=c.id)
    # Maps (image + generated thumbnail) → their campaign.
    map_campaign: dict = {}
    for m in db.query(Map).all():
        map_campaign[m.id] = m.campaign_id
        _add(m.image_url, campaign_id=m.campaign_id)
        _add(getattr(m, "thumbnail_url", None), campaign_id=m.campaign_id)
    # Tokens → via map → campaign.
    for t in db.query(Token).all():
        _add(t.image_url, campaign_id=map_campaign.get(t.map_id))
    # Characters → campaign, or owner for standalone (no campaign).
    for ch in db.query(Character).all():
        if ch.campaign_id is not None:
            _add(ch.portrait_url, campaign_id=ch.campaign_id)
        else:
            _add(ch.portrait_url, user_id=ch.owner_user_id)
    for tt in db.query(TokenTemplate).all():
        _add(tt.image_url, campaign_id=tt.campaign_id)
    for e in db.query(Encounter).all():
        _add(e.background_url, campaign_id=e.campaign_id)
    for h in db.query(Handout).all():
        _add(h.image_url, campaign_id=h.campaign_id)
        # v2.1046.0 — document attachments (v2.1045.0) share the handouts
        # subdir; without this they walked as "unattributed" bytes and
        # escaped per-campaign quota enforcement.
        _add(getattr(h, "file_url", None), campaign_id=h.campaign_id)
    # Audio → via playlist → campaign.
    playlist_campaign = {p.id: p.campaign_id for p in db.query(Playlist).all()}
    for tr in db.query(PlaylistTrack).all():
        _add(tr.file_url, campaign_id=playlist_campaign.get(tr.playlist_id))

    campaign_meta = {
        c.id: {"name": c.name, "gm_user_id": c.gm_user_id}
        for c in db.query(Campaign).all()
    }
    user_email = {u.id: u.email for u in db.query(User).all()}
    return index, campaign_meta, user_email


def read_storage(uploads_root=None) -> dict:
    """Return the storage report, or ``{available: False, reason}`` when the
    DB is unreachable. On-demand (no cache); the operator box is small."""
    try:
        from ..database import SessionLocal
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"DB layer unavailable: {e}"}
    root = Path(uploads_root) if uploads_root else _uploads_root()
    try:
        with SessionLocal() as db:
            index, campaign_meta, user_email = _build_index(db)
    except Exception as e:  # noqa: BLE001 — DB down / mid-migration
        return {"available": False, "reason": f"DB query failed: {e}"}
    return aggregate(root, index, campaign_meta, user_email)
