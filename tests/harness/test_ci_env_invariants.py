"""Invariants the CI workflow's `.env` blocks must satisfy.

v2.1047.1 (uploads) + v2.1047.5 (demo reset). Both are the same shape of
bug: a CI env value that makes a whole slice of the suite meaningless
without anything failing loudly, and that reopens silently when a new job
is copy-pasted from an old one.

## 1. Uploads must be enabled (v2.1047.1)

``docker-compose.yml`` defaults ``DEMO_DISABLE_UPLOADS`` to **true**
(``${DEMO_DISABLE_UPLOADS:-true}``), and the gate fires whenever that is
on *and* ``DEMO_MODE`` is on. The harness workflow needs ``DEMO_MODE``
for the seeded demo PCs the tests assert against — so before this fix,
every upload endpoint in CI answered
``403 "Uploads are disabled on this demo instance"`` and every
upload-exercising test was red: 9 harness files post multipart uploads
(handouts, handout documents, media gate, bulk map upload, encounter
background, map grid/scale/weather/letterbox, export) plus two
admin-center storage tests.

That is a hole in the regression gate rather than a product bug, and it
is exactly the kind that reopens silently — a new CI job copy-pasted
from an old one inherits the old env block. Hence this test: it parses
the workflow and asserts the invariant directly.

**The guard itself stays covered.** Disabling the *demo lockdown* in CI
does not stop CI from testing the lockdown:
``test_demo_disable_uploads.py::test_all_upload_endpoints_carry_the_guard``
is pure route introspection (no HTTP, config-independent), and its live
HTTP test deliberately accepts either 200 or 403 so it exercises the
wiring under either configuration.

## 2. The demo reset must not fire mid-run (v2.1047.5)

``DEMO_MODE=true`` spawns an unconditional
``while True: sleep(interval); reset_and_reseed()`` scheduler
(``app/demo_scheduler.py``) that **wipes and reseeds the dataset**. CI
needs ``DEMO_MODE`` for the seeded PCs its assertions reference, but at
the previous ``DEMO_RESET_INTERVAL_MINUTES=60`` the harness job — **272
minutes** in run 31070630004 — absorbed roughly four full wipes while
tests were running. The damage is diffuse and hard to read back to a
cause: tokens vanish (``"Token not found"``), distances get measured
from reseeded positions, sessions 401 after users are recreated, and
buffs/HP reset under a running test.

The interval is clamped to ``[5, 1440]`` in ``config.py``, so there is no
true "off" — 1440 (24h) is the maximum and means "never" for any
plausible run. ``DEMO_RESET_ON_BOOT`` still gives each job its fresh
seed.
"""
import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-harness.yml"

_HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)EOF\1\s*$")


def _workflow_text() -> str:
    return _WORKFLOW.read_text()


def _env_heredoc_blocks() -> list[str]:
    """Each ``cat > .env <<EOF ... EOF``-style block in the workflow.

    The workflow writes its ``.env`` inline per job, so the env vars live
    in shell heredocs rather than in YAML ``env:`` maps — parsing the
    YAML alone wouldn't see them.
    """
    # The workflow uses a *quoted* delimiter (``cat > .env <<'EOF'``), so
    # matching a bare trailing "EOF" finds nothing — which is how the
    # first draft of this test passed vacuously. `_START_RE` handles the
    # quoted, double-quoted, and bare forms.
    blocks, current = [], None
    for line in _workflow_text().splitlines():
        stripped = line.strip()
        if current is None:
            if _HEREDOC_START_RE.search(stripped):
                current = []
        else:
            if stripped in ("EOF", "'EOF'", '"EOF"'):
                blocks.append("\n".join(current))
                current = None
            else:
                current.append(stripped)
    return blocks


def test_workflow_is_valid_yaml():
    """A malformed workflow silently stops running rather than failing
    loudly, so parse it."""
    assert _WORKFLOW.is_file(), f"missing workflow: {_WORKFLOW}"
    parsed = yaml.safe_load(_workflow_text())
    assert isinstance(parsed, dict) and parsed.get("jobs"), (
        "workflow has no jobs — did the YAML break?")


def test_every_demo_mode_env_block_enables_uploads():
    """**The invariant.** Any CI env block that turns on ``DEMO_MODE``
    must also set ``DEMO_DISABLE_UPLOADS=false``, or every upload
    endpoint 403s and the upload tests never actually run."""
    offenders = []
    for i, block in enumerate(_env_heredoc_blocks()):
        if "DEMO_MODE=true" not in block:
            continue
        if "DEMO_DISABLE_UPLOADS=false" not in block:
            offenders.append(i)
    assert not offenders, (
        f"{len(offenders)} CI env block(s) set DEMO_MODE=true without "
        "DEMO_DISABLE_UPLOADS=false — every upload endpoint will answer "
        "403 and the upload tests will be vacuously red. Add "
        "DEMO_DISABLE_UPLOADS=false to those blocks."
    )


def test_demo_mode_env_blocks_exist():
    """Guard the guard: if the workflow stops writing .env via heredocs
    the test above would pass vacuously."""
    blocks = [b for b in _env_heredoc_blocks() if "DEMO_MODE=true" in b]
    assert len(blocks) >= 4, (
        f"expected the workflow's 4 jobs to each seed DEMO_MODE=true; "
        f"found {len(blocks)} — has the env-writing shape changed?"
    )


def test_compose_still_defaults_uploads_disabled():
    """The CI override only matters because the shipped default is
    locked down. If that default ever flips, this test's premise (and
    the demo's safety posture) changed and should be re-reviewed."""
    compose = yaml.safe_load((_REPO_ROOT / "docker-compose.yml").read_text())
    app_env = ((compose.get("services") or {}).get("app") or {}).get("env", {})
    app_env = ((compose.get("services") or {}).get("app") or {}).get(
        "environment", app_env)
    raw = str(app_env.get("DEMO_DISABLE_UPLOADS", ""))
    assert ":-true}" in raw, (
        "docker-compose no longer defaults DEMO_DISABLE_UPLOADS to true "
        f"(got {raw!r}) — re-check the demo lockdown posture."
    )

# ── Invariant 2: the demo reset must not fire mid-run ────────────────

# config.py clamps DEMO_RESET_INTERVAL_MINUTES to [5, 1440], so 1440 is
# the effective "never". Anything at or above the longest plausible job
# is acceptable; the CI workflow uses the maximum.
_MIN_SAFE_RESET_MINUTES = 720


def _reset_interval(block: str) -> "int | None":
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("DEMO_RESET_INTERVAL_MINUTES="):
            try:
                return int(line.split("=", 1)[1].strip())
            except ValueError:
                return None
    return None


def test_demo_reset_cannot_fire_during_a_ci_run():
    """**The invariant.** Any CI env block enabling DEMO_MODE must set a
    reset interval long enough that the scheduler never fires mid-run.

    At 60 minutes the 272-minute harness job took ~4 dataset wipes while
    tests were executing (CI run 31070630004), producing vanished
    tokens, reseeded positions, 401s and reset buffs — all of which read
    as unrelated product bugs.
    """
    offenders = []
    for i, block in enumerate(_env_heredoc_blocks()):
        if "DEMO_MODE=true" not in block:
            continue
        got = _reset_interval(block)
        if got is None or got < _MIN_SAFE_RESET_MINUTES:
            offenders.append(f"block {i}: DEMO_RESET_INTERVAL_MINUTES={got}")
    assert not offenders, (
        "CI env block(s) let the demo scheduler wipe the dataset mid-run: "
        + "; ".join(offenders)
        + f". Set it to >= {_MIN_SAFE_RESET_MINUTES} (the workflow uses 1440, "
          "the clamp's maximum). DEMO_RESET_ON_BOOT still seeds each job.")


def test_demo_reset_on_boot_still_enabled():
    """The fix must not throw out the seed with the scheduler — the
    suite's assertions reference the demo PCs, so each job still needs a
    freshly-seeded dataset at startup."""
    blocks = [b for b in _env_heredoc_blocks() if "DEMO_MODE=true" in b]
    assert blocks, "no DEMO_MODE env blocks found"
    missing = [i for i, b in enumerate(blocks)
               if "DEMO_RESET_ON_BOOT=true" not in b]
    assert not missing, (
        f"blocks {missing} enable DEMO_MODE without DEMO_RESET_ON_BOOT=true "
        "— those jobs would run against whatever state the volume held")


def test_reset_interval_is_within_the_config_clamp():
    """A value above 1440 would be silently clamped back down, so the
    workflow would look fixed while the scheduler still fired."""
    for i, block in enumerate(_env_heredoc_blocks()):
        if "DEMO_MODE=true" not in block:
            continue
        got = _reset_interval(block)
        assert got is not None and 5 <= got <= 1440, (
            f"block {i}: DEMO_RESET_INTERVAL_MINUTES={got} is outside "
            "config.py's max(5, min(1440, ...)) clamp — it would be "
            "silently rewritten and the guard above would pass falsely")
