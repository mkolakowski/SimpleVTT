"""v2.482.0 — GDPR Article 15 / 20 self-serve data export.

``GET /api/users/me/export`` returns the authenticated user's full
record set as a single JSON archive. This file covers:

  * happy path — 200 + the archive shape a data subject (and the
    privacy policy Section 5.1) expects, including the deliberate
    omission of the password hash / Google SSO id.
  * error path — 401 for an unauthenticated caller.
  * the pure rate-limit helper (``export_cooldown_remaining``) in
    process, since the live 429 path is bypassed under TEST_MODE.

The live endpoint test relies on the harness container running
TEST_MODE=true (which bypasses the per-user cooldown so repeated
runs stay deterministic).
"""
import httpx

from app.user_export import export_cooldown_remaining

from .helpers import BASE_URL


# ---- live endpoint --------------------------------------------------

async def test_export_happy_path(alice_client: httpx.AsyncClient):
    """200 + the archive top-level shape, with account + preferences +
    the credential-omission booleans."""
    resp = await alice_client.get("/api/users/me/export")
    assert resp.status_code == 200, resp.text

    # Saved-as-a-file disposition for browsers hitting the URL directly.
    assert "attachment" in resp.headers.get("content-disposition", "")

    body = resp.json()
    for key in (
        "export_format_version",
        "app_version",
        "generated_for_user_id",
        "account",
        "campaigns_owned",
        "campaign_memberships",
        "characters",
        "dice_rolls",
    ):
        assert key in body, f"export archive missing top-level key {key!r}"

    acct = body["account"]
    assert acct["email"] == "demo-alice@example.com"
    assert acct["role"] in ("admin", "user")
    # The export must NEVER carry credential material.
    assert "password_hash" not in acct
    assert "google_sub" not in acct
    # …but it surfaces which sign-in methods exist as booleans.
    assert isinstance(acct["has_password"], bool)
    assert isinstance(acct["has_google_sso"], bool)
    # Preferences block is present + carries the theme.
    assert "theme" in acct["preferences"]

    # The collection keys are lists (possibly empty, but typed).
    assert isinstance(body["characters"], list)
    assert isinstance(body["dice_rolls"], list)


async def test_export_generated_for_self(alice_client: httpx.AsyncClient):
    """The archive is scoped to the caller — generated_for_user_id
    matches the account id, never another user's."""
    resp = await alice_client.get("/api/users/me/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["generated_for_user_id"] == body["account"]["id"]


async def test_export_requires_auth():
    """An unauthenticated caller is rejected (401), not handed an empty
    or someone-else's archive."""
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=10.0, follow_redirects=False,
    ) as client:
        resp = await client.get(
            "/api/users/me/export",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 401


# ---- pure cooldown helper (the 429 path) ----------------------------

def test_cooldown_zero_when_never_exported():
    assert export_cooldown_remaining(
        now=1000.0, last_export_at=None, cooldown_seconds=86400,
    ) == 0


def test_cooldown_zero_when_window_elapsed():
    # Exported 25h ago, 24h window → allowed.
    assert export_cooldown_remaining(
        now=100_000.0, last_export_at=100_000.0 - 90_000, cooldown_seconds=86400,
    ) == 0


def test_cooldown_positive_within_window():
    # Exported 1h ago, 24h window → ~23h remaining.
    remaining = export_cooldown_remaining(
        now=100_000.0, last_export_at=100_000.0 - 3600, cooldown_seconds=86400,
    )
    assert remaining == 86400 - 3600


def test_cooldown_disabled_when_window_nonpositive():
    # cooldown_seconds <= 0 disables the gate entirely.
    assert export_cooldown_remaining(
        now=100.0, last_export_at=99.0, cooldown_seconds=0,
    ) == 0
