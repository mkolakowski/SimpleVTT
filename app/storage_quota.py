"""Per-user / per-campaign upload-storage quota enforcement.

Arc B2 of ``docs/plans/app-wide-roles-and-storage.md``. Called by the
upload routes BEFORE writing a file: ``check_quota`` returns a human error
string if adding ``new_bytes`` would push the file's campaign (or the
campaign's GM user) over its configured ``storage_limit_bytes``, else None.

Limits default to unlimited (NULL/0), so the common path is a **fast no-op**
— we only run the (potentially expensive) storage scan when a relevant limit
is actually set. Fails **open**: if the accounting layer is unavailable we
allow the upload rather than block legitimate work.
"""
from __future__ import annotations

from typing import Optional


def _human(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def check_quota(
    db, campaign_id: Optional[int], new_bytes: int, *, owner_user_id: Optional[int] = None
) -> Optional[str]:
    """Return an error message if ``new_bytes`` would exceed the campaign's
    or the responsible user's storage limit; else None.

    ``campaign_id`` attributes the file to a campaign (→ its GM user).
    ``owner_user_id`` is the fallback owner for campaign-less uploads
    (e.g. a standalone character portrait).
    """
    from .models import Campaign, User

    camp_limit = None
    gm_id = owner_user_id
    if campaign_id is not None:
        c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if c is not None:
            camp_limit = c.storage_limit_bytes
            gm_id = c.gm_user_id
    user_limit = None
    if gm_id is not None:
        u = db.query(User).filter(User.id == gm_id).first()
        if u is not None:
            user_limit = u.storage_limit_bytes

    # Fast path: no limit set anywhere → nothing to enforce (no scan).
    if not camp_limit and not user_limit:
        return None

    try:
        from .admin_center import storage as _storage
        report = _storage.read_storage()
    except Exception:  # noqa: BLE001 — accounting unavailable → fail open
        return None
    if not report.get("available"):
        return None

    if camp_limit and camp_limit > 0:
        used = next((c["bytes"] for c in report["by_campaign"] if c["campaign_id"] == campaign_id), 0)
        if used + new_bytes > camp_limit:
            return (
                f"Campaign storage limit reached: {_human(used)} used + "
                f"{_human(new_bytes)} > {_human(camp_limit)} limit."
            )
    if user_limit and user_limit > 0 and gm_id is not None:
        used = next((u["bytes"] for u in report["by_user"] if u["user_id"] == gm_id), 0)
        if used + new_bytes > user_limit:
            return (
                f"User storage limit reached: {_human(used)} used + "
                f"{_human(new_bytes)} > {_human(user_limit)} limit."
            )
    return None
