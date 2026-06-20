"""v2.471.0 — Phase 4c of
``docs/plans/fail2ban-crowdsec-integration.md``. Verifies the
env-driven jail-threshold wiring.

Phase 4c lifts the previously-hardcoded jail thresholds
(`maxretry`, `findtime`, `bantime`, `logpath`) into envsubst
placeholders in the jail config + matching FAIL2BAN_* env vars in
`.env.example` + docker-compose.yml. The render-jail.sh entrypoint
resolves the placeholders at container start.

Tests:
- The reference jail config uses the envsubst placeholders (no
  hardcoded numerics).
- .env.example carries every FAIL2BAN_* default the jail expects.
- docker-compose.yml passes every FAIL2BAN_* through to the
  fail2ban service environment block.
- The render-jail.sh helper exists, is executable, and is mounted
  into the fail2ban container.
- Phase 4c changes the jail.d mount to `:/etc/fail2ban/jail.d.template`
  (read-only template path) — the env-rendered output lives in a
  writable directory inside the container.
"""
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_JAIL_CONFIG = _REPO_ROOT / "docs/integrations/fail2ban/jail.d/simplevtt.conf"
_RENDER_SCRIPT = _REPO_ROOT / "docs/integrations/fail2ban/scripts/render-jail.sh"

# The FAIL2BAN_* placeholders the jail config + .env.example +
# docker-compose.yml must keep in lockstep.
_REQUIRED_PLACEHOLDERS = {
    "FAIL2BAN_AUDIT_LOG_PATH",
    "FAIL2BAN_LOGIN_MAXRETRY",
    "FAIL2BAN_LOGIN_FINDTIME",
    "FAIL2BAN_LOGIN_BANTIME",
}

# Subset that needs a default in .env.example (audit log path
# inherits from AUDIT_LOG_PATH so it's not in this set).
_ENV_EXAMPLE_DEFAULTS = {
    "FAIL2BAN_LOGIN_MAXRETRY",
    "FAIL2BAN_LOGIN_FINDTIME",
    "FAIL2BAN_LOGIN_BANTIME",
    "FAIL2BAN_MAGIC_LINK_REPLAY_BANTIME",
    "FAIL2BAN_API_PROBE_MAXRETRY",
    "FAIL2BAN_DEFAULT_BANTIME",
}


def _load_compose() -> dict:
    with _COMPOSE.open() as f:
        return yaml.safe_load(f)


def _load_jail() -> str:
    return _JAIL_CONFIG.read_text()


def _load_env_example() -> str:
    return _ENV_EXAMPLE.read_text()


def test_jail_config_uses_envsubst_placeholders():
    """The shipped jail config has env-templated thresholds; no
    hardcoded ``maxretry = 5`` or numeric ``bantime`` lines that
    would silently override the env vars."""
    jail = _load_jail()
    for placeholder in _REQUIRED_PLACEHOLDERS:
        assert f"${{{placeholder}}}" in jail, (
            f"jail config missing required placeholder "
            f"${{{placeholder}}}"
        )
    # No hardcoded ``maxretry = 5`` style override.
    for line in jail.splitlines():
        if line.strip().startswith("#"):
            continue
        if line.strip().startswith("maxretry"):
            assert "${FAIL2BAN_LOGIN_MAXRETRY}" in line, (
                f"jail line {line!r} hardcodes maxretry; must use "
                "the FAIL2BAN_LOGIN_MAXRETRY placeholder"
            )


def test_env_example_carries_fail2ban_defaults():
    """Every FAIL2BAN_* knob in _ENV_EXAMPLE_DEFAULTS has a default
    in .env.example so an operator can copy .env.example → .env and
    have the fail2ban profile work out of the box."""
    env_example = _load_env_example()
    for var in _ENV_EXAMPLE_DEFAULTS:
        # Match an uncommented `VAR=...` line.
        found = False
        for line in env_example.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0]
            if key == var:
                found = True
                break
        assert found, (
            f"FAIL2BAN_* env var {var} missing from .env.example "
            "(an operator copying the example file will start fail2ban "
            "with an empty placeholder)"
        )


def test_compose_passes_fail2ban_env_vars():
    """The fail2ban service's environment block plumbs every
    FAIL2BAN_* placeholder through from the host shell."""
    compose = _load_compose()
    env = compose["services"]["fail2ban"].get("environment") or {}
    # Convert list-style envs to a dict for uniform lookup.
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)
    for placeholder in _REQUIRED_PLACEHOLDERS | _ENV_EXAMPLE_DEFAULTS:
        assert placeholder in env, (
            f"docker-compose fail2ban environment block missing "
            f"{placeholder}"
        )


def test_render_script_exists_and_is_executable():
    """The render-jail.sh helper is shipped + executable so the
    container entrypoint can `exec /scripts/render-jail.sh` cleanly."""
    assert _RENDER_SCRIPT.is_file(), (
        f"render-jail.sh missing at {_RENDER_SCRIPT}"
    )
    import os
    mode = _RENDER_SCRIPT.stat().st_mode
    assert mode & 0o100, (
        f"render-jail.sh must be executable (mode={oct(mode)})"
    )


def test_compose_uses_render_jail_entrypoint():
    """The fail2ban service overrides the image entrypoint to run
    render-jail.sh before fail2ban-server."""
    compose = _load_compose()
    entrypoint = compose["services"]["fail2ban"].get("entrypoint") or []
    assert entrypoint, (
        "fail2ban service must define entrypoint to run render-jail.sh"
    )
    # Match either string or list form.
    if isinstance(entrypoint, str):
        assert "render-jail.sh" in entrypoint
    else:
        assert any("render-jail.sh" in str(e) for e in entrypoint), (
            f"entrypoint must invoke render-jail.sh; got {entrypoint}"
        )


def test_compose_mounts_jail_as_template():
    """The jail config mounts as a read-only template (so the
    render-jail.sh entrypoint can copy + envsubst into the writable
    output path)."""
    compose = _load_compose()
    volumes = compose["services"]["fail2ban"].get("volumes") or []
    template_mount = next(
        (v for v in volumes
         if isinstance(v, str)
         and "fail2ban/jail.d:" in v
         and "jail.d.template" in v),
        None,
    )
    assert template_mount is not None, (
        "fail2ban must mount docs/integrations/fail2ban/jail.d at "
        "/etc/fail2ban/jail.d.template (read-only template path) so "
        "render-jail.sh can envsubst into a separate writable "
        "destination; got volumes=" + str(volumes)
    )
    assert ":ro" in template_mount, (
        f"jail.d template mount must be read-only; got {template_mount}"
    )


def test_compose_mounts_render_script():
    """The render-jail.sh helper is mounted into /scripts/ inside
    the fail2ban container (read-only)."""
    compose = _load_compose()
    volumes = compose["services"]["fail2ban"].get("volumes") or []
    script_mount = next(
        (v for v in volumes
         if isinstance(v, str)
         and "render-jail.sh" in v),
        None,
    )
    assert script_mount is not None, (
        "fail2ban must mount the render-jail.sh helper into the "
        "container; got volumes=" + str(volumes)
    )
    assert ":ro" in script_mount, (
        f"render-jail.sh mount must be read-only; got {script_mount}"
    )
