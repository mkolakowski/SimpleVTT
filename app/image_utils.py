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
