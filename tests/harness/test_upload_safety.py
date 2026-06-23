"""v2.599.4 — regression tests for the upload-extension allowlist.

Several upload endpoints validated only the attacker-controlled multipart
Content-Type header, then derived the on-disk extension from the user filename
with no allowlist. Files are served from /static with the response
Content-Type guessed from the extension, so `Content-Type: image/png` +
`filename=x.html` was written + served as text/html → stored XSS.
`app/upload_safety.safe_ext` now gates the extension. Pure in-process (no
container, no fastapi — the module ships an HTTPException shim host-side).
"""
from __future__ import annotations

from pathlib import Path

from app import upload_safety as us
from app.upload_safety import AUDIO_EXTS, IMAGE_EXTS, IMAGE_VIDEO_EXTS, safe_ext


def _raises_400(fn):
    try:
        fn()
    except us.HTTPException as exc:  # the real or shimmed type
        return getattr(exc, "status_code", None) == 400
    return False


def test_allowed_image_ext_passes_and_lowercases():
    assert safe_ext("map.png", IMAGE_EXTS) == ".png"
    assert safe_ext("MAP.PNG", IMAGE_EXTS) == ".png"
    assert safe_ext("a.JPEG", IMAGE_EXTS) == ".jpeg"


def test_no_suffix_falls_back_to_default():
    assert safe_ext("noext", IMAGE_EXTS) == ".png"
    assert safe_ext("", IMAGE_EXTS) == ".png"
    assert safe_ext(None, IMAGE_EXTS) == ".png"
    assert safe_ext("song", AUDIO_EXTS, default=".mp3") == ".mp3"


def test_dangerous_extensions_are_rejected():
    # The core of the fix: html/svg/js can't ride in on a spoofed Content-Type.
    for bad in ("evil.html", "evil.svg", "evil.htm", "evil.js", "evil.xml", "evil.php"):
        assert _raises_400(lambda b=bad: safe_ext(b, IMAGE_EXTS)), bad


def test_video_only_in_image_video_set():
    assert safe_ext("clip.mp4", IMAGE_VIDEO_EXTS) == ".mp4"
    assert safe_ext("clip.webm", IMAGE_VIDEO_EXTS) == ".webm"
    assert _raises_400(lambda: safe_ext("clip.mp4", IMAGE_EXTS))  # not in image-only


def test_audio_set_rejects_non_audio():
    assert safe_ext("track.mp3", AUDIO_EXTS, default=".mp3") == ".mp3"
    assert _raises_400(lambda: safe_ext("track.html", AUDIO_EXTS, default=".mp3"))


def test_vulnerable_sites_route_through_safe_ext():
    """Wiring guard: the upload sites that derived the extension from the raw
    filename now go through the allowlist (helper call or, in the redirect-style
    admin-center handler, the IMAGE_VIDEO_EXTS constant)."""
    root = Path(__file__).resolve().parents[2]
    for rel in ("app/routes/tabletop_routes.py",
                "app/routes/admin_routes.py",
                "app/routes/audio_routes.py"):
        assert "safe_ext(" in (root / rel).read_text(), f"{rel} should call safe_ext"
    ac = (root / "app/admin_center/main.py").read_text()
    assert "IMAGE_VIDEO_EXTS" in ac, "admin-center map upload should gate on IMAGE_VIDEO_EXTS"
