"""YAML syntax + schema validation for the CrowdSec configs at
``docs/integrations/crowdsec/`` (Phase 2 of
``docs/plans/fail2ban-crowdsec-integration.md``).

These tests are pure in-process — they don't run a CrowdSec
container. They parse each YAML file and assert the keys CrowdSec
itself requires + the SimpleVTT-specific conventions documented
in ``docs/integrations/crowdsec/README.md``. Catches a typo'd
filter expression or a missing label before an operator copies
the file into ``/etc/crowdsec/`` and reloads.

A real end-to-end smoke test that brings up a CrowdSec container,
replays synthetic events, and asserts the scenarios fire via
``cscli decisions list`` is filed as Phase 2B — gated on the
CrowdSec image being reliably available from Docker Hub.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CROWDSEC_DIR = _REPO_ROOT / "docs" / "integrations" / "crowdsec"


def _scenarios() -> list[Path]:
    return sorted((_CROWDSEC_DIR / "scenarios").glob("*.yaml"))


def _parsers() -> list[Path]:
    return sorted((_CROWDSEC_DIR / "parsers").rglob("*.yaml"))


def test_crowdsec_dir_exists():
    assert _CROWDSEC_DIR.is_dir(), (
        "docs/integrations/crowdsec/ missing — Phase 2 configs not shipped"
    )


def test_parsers_present():
    parsers = _parsers()
    assert parsers, "no parser YAMLs found under docs/integrations/crowdsec/parsers/"
    # We ship one parser today; if a second lands, update the count here.
    assert len(parsers) >= 1


def test_scenarios_present():
    scenarios = _scenarios()
    # README documents 5 scenarios; assert at least that many.
    assert len(scenarios) >= 5, f"expected >= 5 scenarios; got {len(scenarios)}: {scenarios}"


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_yaml_parses(path: Path):
    """Every scenario file must be valid YAML."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), f"{path.name}: not a YAML mapping"


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_has_required_keys(path: Path):
    """CrowdSec scenario YAML schema requires these top-level keys.
    A missing key causes the scenario to be silently ignored when
    CrowdSec reloads — assertion here catches it before an operator
    copies the file."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    required = {"type", "name", "filter", "groupby", "blackhole", "labels"}
    missing = required - set(doc.keys())
    assert not missing, f"{path.name}: missing required keys: {missing}"


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_type_is_valid(path: Path):
    """``type`` must be one of CrowdSec's known scenario shapes.
    Phase 2 uses ``leaky`` (rate-based bucket) and ``trigger``
    (fires on first match)."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    assert doc["type"] in {"leaky", "trigger", "counter"}, (
        f"{path.name}: unknown scenario type {doc['type']!r}"
    )


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_name_is_namespaced(path: Path):
    """SimpleVTT scenarios should be namespaced ``simplevtt/<slug>``
    so an operator running multiple CrowdSec services can tell which
    deployment a decision came from."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    assert doc["name"].startswith("simplevtt/"), (
        f"{path.name}: scenario name {doc['name']!r} must start with 'simplevtt/'"
    )


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_labels_have_service_simplevtt(path: Path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    labels = doc.get("labels") or {}
    assert labels.get("service") == "simplevtt", (
        f"{path.name}: labels.service should be 'simplevtt'"
    )


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_remediation_flag_set(path: Path):
    """``labels.remediation: true`` is the standard CrowdSec hint
    that a bouncer should actually act on this decision (rather
    than just log it). Every shipped SimpleVTT scenario is meant to
    drive a ban, so the flag must be true."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    labels = doc.get("labels") or {}
    assert labels.get("remediation") is True, (
        f"{path.name}: labels.remediation should be True for shipped scenarios"
    )


@pytest.mark.parametrize("path", _scenarios())
def test_scenario_filter_references_simplevtt_log(path: Path):
    """Every shipped scenario should filter by the parser's
    ``evt.Meta.log_type == 'simplevtt-audit'`` tag — otherwise it
    would silently fire on unrelated CrowdSec events."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    assert "simplevtt-audit" in doc["filter"], (
        f"{path.name}: filter must reference 'simplevtt-audit' log_type"
    )


@pytest.mark.parametrize("path", _scenarios())
def test_leaky_scenarios_have_capacity_and_leakspeed(path: Path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    if doc["type"] != "leaky":
        pytest.skip(f"{path.name} is a {doc['type']} scenario")
    assert "capacity" in doc, f"{path.name}: leaky scenario needs capacity"
    assert "leakspeed" in doc, f"{path.name}: leaky scenario needs leakspeed"
    assert isinstance(doc["capacity"], int), (
        f"{path.name}: capacity must be an int"
    )


@pytest.mark.parametrize("path", _parsers())
def test_parser_yaml_parses(path: Path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    assert isinstance(doc, dict), f"{path.name}: not a YAML mapping"


@pytest.mark.parametrize("path", _parsers())
def test_parser_has_required_keys(path: Path):
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    required = {"name", "filter", "nodes"}
    missing = required - set(doc.keys())
    assert not missing, f"{path.name}: missing required keys: {missing}"


@pytest.mark.parametrize("path", _parsers())
def test_parser_has_audit_log_type_static(path: Path):
    """The simplevtt parser MUST set ``evt.Meta.log_type =
    'simplevtt-audit'`` so the scenario filters above match. A
    parser that drops the static would silently disable every
    scenario downstream."""
    with open(path) as fh:
        doc = yaml.safe_load(fh)
    found = False
    for node in doc.get("nodes") or []:
        for static in node.get("statics") or []:
            if static.get("meta") == "log_type" and static.get("value") == "simplevtt-audit":
                found = True
                break
    assert found, (
        f"{path.name}: parser must emit a static "
        "meta=log_type value=simplevtt-audit"
    )


def test_readme_documents_all_scenarios():
    """The README's scenario table must mention every shipped
    scenario by name so an operator copy-pasting from the docs
    finds the file. Catches a doc-vs.-files drift."""
    readme = (_CROWDSEC_DIR / "README.md").read_text()
    for path in _scenarios():
        with open(path) as fh:
            doc = yaml.safe_load(fh)
        assert doc["name"] in readme, (
            f"README missing scenario name {doc['name']!r} (from {path.name})"
        )
