"""v2.1047.1 — CI must exercise the upload endpoints, not 403 past them.

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
