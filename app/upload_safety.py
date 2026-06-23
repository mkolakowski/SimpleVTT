"""Shared upload-extension allowlist — security fix (v2.599.4).

Several upload endpoints validated only the attacker-controlled multipart
``Content-Type`` header, then derived the on-disk file extension from the
user-supplied *filename* with no allowlist. Uploaded files are served from the
``/static`` mount, where Starlette sets the response ``Content-Type`` from the
file **extension** (``mimetypes.guess_type``). So an attacker could send
``Content-Type: image/png`` (passing the type check) together with
``filename=x.html`` (or ``x.svg``) and have the file served back as
``text/html`` / ``image/svg+xml`` — a stored, same-origin XSS.

``safe_ext`` validates the extension against a strict allowlist and raises
``HTTPException(400)`` on anything else. Endpoints that already gate on an
extension allowlist (portrait, token-template, handout) are equivalent and
left as-is.
"""
from __future__ import annotations

from pathlib import Path

try:  # real type in-app; shim host-side where fastapi isn't installed (unit tests)
    from fastapi import HTTPException
except Exception:  # pragma: no cover - exercised only in host-side unit tests
    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int = 400, detail: str = ""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)


# Canonical allowlists. Keep in sync with the matching Content-Type sets at
# each call site (images, images+video for maps/backgrounds, audio).
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_VIDEO_EXTS = IMAGE_EXTS | {".webm", ".mp4"}
AUDIO_EXTS = {".mp3", ".ogg", ".oga", ".wav", ".m4a", ".aac"}


def safe_ext(filename, allowed, *, default: str = ".png", message: str = "Unsupported file type") -> str:
    """Return the lowercased extension of ``filename`` when it is in
    ``allowed``; otherwise raise ``HTTPException(400, message)``.

    Falls back to ``default`` (which must itself be in ``allowed``) when the
    filename has no suffix. The returned value is the only thing that should
    decide the on-disk extension — never the raw filename — so a spoofed
    Content-Type can't smuggle an ``.html`` / ``.svg`` past the type check.
    """
    ext = Path(filename or "").suffix.lower() or default
    if ext not in allowed:
        raise HTTPException(400, message)
    return ext
