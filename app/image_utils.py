"""Image helpers for SimpleVTT.

Currently: average-colour computation for the per-map letterbox/surround
background (v2.733.0). Shared by the GM toggle endpoint and demo seeding so
both compute the colour the same way.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# ``app/static`` — this module lives at ``app/image_utils.py`` so the static
# root is a sibling ``static/`` directory.
_STATIC_DIR = (Path(__file__).resolve().parent / "static").resolve()


def _resolve_static(image_url: Optional[str]) -> Optional[Path]:
    """Resolve a ``/static/...`` URL to a filesystem path inside the static
    root, or None (external URL / traversal / missing file)."""
    if not image_url or not image_url.startswith("/static/"):
        return None
    rel = image_url[len("/static/"):].split("?", 1)[0].split("#", 1)[0]
    path = (_STATIC_DIR / rel).resolve()
    try:
        path.relative_to(_STATIC_DIR)
    except ValueError:
        return None
    return path if path.is_file() else None


def natural_image_dims(image_url: Optional[str]) -> Optional[tuple]:
    """v2.859.0 — the natural ``(width, height)`` of a ``/static``-hosted image,
    or None. Demo seeding sets a map's ``width_px``/``height_px`` from this so
    the stored dimensions equal the image's real resolution — the invariant the
    map editor + upload flow assume, keeping editor and tabletop coordinates in
    the same pixel space."""
    path = _resolve_static(image_url)
    if not path:
        return None
    try:
        from PIL import Image
        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None


def average_image_color(image_url: Optional[str]) -> Optional[str]:
    """Average colour of a ``/static``-hosted image as ``#rrggbb``.

    Returns ``None`` for empty/external URLs, paths that escape the static
    root, missing files, or any decode error — callers treat ``None`` as
    "no override" (the default dark letterbox). Only local ``/static/...``
    paths are resolved; remote URLs are intentionally not fetched.
    """
    if not image_url or not image_url.startswith("/static/"):
        return None
    rel = image_url[len("/static/"):].split("?", 1)[0].split("#", 1)[0]
    path = (_STATIC_DIR / rel).resolve()
    # Containment guard — never read outside the static tree.
    try:
        path.relative_to(_STATIC_DIR)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            # Downscale first so ImageStat is cheap on large battle maps;
            # the mean of a 64px thumbnail tracks the full-image average.
            rgb.thumbnail((64, 64))
            r, g, b = ImageStat.Stat(rgb).mean
        return f"#{int(round(r)):02x}{int(round(g)):02x}{int(round(b)):02x}"
    except Exception:
        return None
