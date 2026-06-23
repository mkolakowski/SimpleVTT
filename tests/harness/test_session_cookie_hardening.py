"""v2.599.7 — session cookie hardening (security review defense-in-depth).

Both the app and the Admin Center set `same_site="lax"` explicitly (blocks the
classic cross-site POST CSRF vector) and an env-driven `Secure` flag
(`SESSION_COOKIE_SECURE`, default off so HTTP dev / the localhost harness still
authenticate). Source + compose-plumbing guards; pure in-process.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]


def test_compose_plumbs_session_cookie_secure_for_both_services():
    compose = yaml.safe_load((_ROOT / "docker-compose.yml").read_text())
    for svc in ("app", "admin-center"):
        env = compose["services"][svc].get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) for e in env if "=" in e)
        assert "SESSION_COOKIE_SECURE" in env, f"{svc} must plumb SESSION_COOKIE_SECURE"


def test_session_middleware_sets_samesite_lax_and_env_driven_secure():
    for rel in ("app/main.py", "app/admin_center/main.py"):
        src = (_ROOT / rel).read_text()
        assert 'same_site="lax"' in src, f"{rel} must set same_site=lax explicitly"
        assert "https_only=_COOKIE_SECURE" in src, f"{rel} must drive https_only from env"
        assert "SESSION_COOKIE_SECURE" in src, f"{rel} must read SESSION_COOKIE_SECURE"


def test_env_example_documents_session_cookie_secure():
    env_example = (_ROOT / ".env.example").read_text()
    found = any(
        ln.strip().split("=", 1)[0] == "SESSION_COOKIE_SECURE"
        for ln in env_example.splitlines()
        if "=" in ln and not ln.strip().startswith("#")
    )
    assert found, "SESSION_COOKIE_SECURE missing from .env.example"
