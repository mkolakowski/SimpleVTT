"""Plain-English explanations for audit-log event tags.

Powers the dashboard's hover help — "why is this line in the log?" —
so an operator doesn't have to memorize the canonical event taxonomy.
Pure + stdlib-only (a dict + a lookup), so it's trivially testable.
"""
from __future__ import annotations

# Exact event-tag → why-it-appears explanation.
EXPLANATIONS: dict[str, str] = {
    "auth.login_ok": (
        "A user signed in successfully. Recorded with the user id (not "
        "the email) so a log leak can't be cross-referenced to addresses."
    ),
    "auth.login_failed": (
        "A sign-in attempt used a bad password or unknown email. A burst "
        "from one IP usually means credential stuffing — the fail2ban "
        "auth jail bans on this event."
    ),
    "auth.signup_failed": (
        "An account-registration attempt was rejected (e.g. duplicate "
        "email, or local registration is disabled)."
    ),
    "demo_magic_link.mint_ok": (
        "An admin minted a one-time demo magic-link login URL."
    ),
    "demo_magic_link.verify_ok": (
        "A demo magic-link login URL was redeemed successfully."
    ),
    "demo_magic_link.verify_rejected": (
        "A demo magic-link was refused — expired, already used, or a bad "
        "signature. Repeated rejections can indicate link-guessing."
    ),
    "api.unauthorized": (
        "A request hit a protected endpoint without being logged in "
        "(HTTP 401). Often a probe for an authenticated API path."
    ),
    "api.forbidden": (
        "A logged-in user tried something their role doesn't allow "
        "(HTTP 403) — e.g. a non-admin hitting an admin endpoint."
    ),
    "api.not_found": (
        "A request hit a path that doesn't exist (HTTP 404). Many distinct "
        "404s from one IP is the classic vulnerability-scanner footprint — "
        "the fail2ban scanner jail bans on this."
    ),
    "visitor.request": (
        "Per-request visitor log (opt-in). One line per HTTP request — "
        "path, method, status, response time. Only present when "
        "VISITOR_REQUEST_LOG_ENABLED is on; the fail2ban flood jail can "
        "rate-ban on it."
    ),
    "user.data_export": (
        "A user pulled their own GDPR data export (Article 15/20). Logged "
        "so a hijacked-session bulk PII pull leaves a trace."
    ),
}

# Prefix → explanation, for tag families with a variable suffix.
_PREFIX_EXPLANATIONS: list[tuple[str, str]] = [
    ("admin.", (
        "An admin performed a destructive or privileged action (create / "
        "disable / delete a user, reset a password, ban an IP). The exact "
        "action is the part after 'admin.'."
    )),
    ("cloudflare.", (
        "A Cloudflare edge ban/unban was pushed via the API — moving a "
        "SimpleVTT-decided ban to (or from) the Cloudflare edge."
    )),
    ("auth.", "An authentication-subsystem event."),
    ("demo_magic_link.", "A demo magic-link login event."),
    ("api.", "An API-surface event (an HTTP error worth noting for banning)."),
]

_GENERIC = (
    "A SimpleVTT audit event. The tag is '<subsystem>.<event>'; this one "
    "isn't in the help catalog yet."
)


def explain(event_tag: str) -> str:
    """Return a why-it-appears explanation for an event tag.

    Exact match first, then the longest matching family prefix, then a
    generic fallback so every tag gets *some* help text.
    """
    if not event_tag:
        return _GENERIC
    if event_tag in EXPLANATIONS:
        return EXPLANATIONS[event_tag]
    for prefix, text in _PREFIX_EXPLANATIONS:
        if event_tag.startswith(prefix):
            return text
    return _GENERIC
