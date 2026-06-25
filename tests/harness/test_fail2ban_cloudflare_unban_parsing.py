"""Regression: the cloudflare-bouncer ``actionunban`` must parse the
Cloudflare access-rules response correctly.

Bug (caught here): the Cloudflare API returns **pretty-printed** JSON —
``"id": "abc"`` with a space after the colon, each field on its own
line. The original ``actionunban`` extracted the rule id with a
compact-only sed (``s/.*"id":"\\([^"]*\\)".*/\\1/p``) that requires
``"id":"`` with NO space, so against the real API it matched **nothing**:
``rule_id`` came back empty, the ``if [ -n "$rule_id" ]`` guard failed,
the DELETE never ran, and the edge ban leaked on every unban. Two latent
traps lurked behind it too — the greedy ``.*`` would have grabbed the
trailing ``scope.id`` instead of the rule id, and deleting the first
match regardless of mode could nuke a legitimate whitelist/allow rule
for the same IP.

The fix parses the JSON with ``python3`` (in the image; no jq) and
deletes only ``mode == "block"`` rules. This test pulls the actual
``python3 -c '...'`` program straight out of the shipped action file and
runs it against a pretty-printed fixture containing a block rule, a
whitelist rule, and ``scope.id`` collisions — asserting it emits only
the block rule's id. It fails against the old sed-based action (no
``python3 -c`` to extract) and passes against the fix.
"""
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ACTION_CONFIG = (
    _REPO_ROOT
    / "docs/integrations/fail2ban/action.d/cloudflare-bouncer.conf"
)

# A realistic, PRETTY-printed Cloudflare access-rules response for one IP:
# a fail2ban block rule, a manual whitelist rule, and a nested scope.id on
# each (the trap the greedy sed fell into). Only the block id should delete.
_PRETTY_RESPONSE = """{
  "result": [
    {
      "id": "BLOCK_RULE_ID",
      "paused": false,
      "mode": "block",
      "notes": "fail2ban simplevtt-scanner banned 9.9.9.9 for 3600s",
      "configuration": {"target": "ip", "value": "9.9.9.9"},
      "scope": {"id": "SCOPE_ID_X", "email": "a@b.c", "type": "user"}
    },
    {
      "id": "WHITELIST_RULE_ID",
      "mode": "whitelist",
      "notes": "Allow_IP_9.9.9.9",
      "configuration": {"target": "ip", "value": "9.9.9.9"},
      "scope": {"id": "SCOPE_ID_X", "email": "a@b.c", "type": "user"}
    }
  ],
  "success": true,
  "errors": [],
  "messages": []
}"""

_EMPTY_RESPONSE = '{"result": [], "success": true}'


def _extract_unban_id_program() -> str:
    """Pull the ``python3 -c '<program>'`` body out of the shipped
    actionunban so the test exercises exactly what ships, not a copy."""
    text = _ACTION_CONFIG.read_text()
    m = re.search(r"python3 -c '([^']*)'", text)
    assert m is not None, (
        "actionunban must parse the rules JSON with a python3 -c program "
        "(the compact-only sed cannot read Cloudflare's pretty JSON)"
    )
    return m.group(1)


def _run(program: str, stdin: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", program],
        input=stdin, capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"extractor errored: {proc.stderr}"
    return proc.stdout.strip()


def test_unban_extractor_picks_block_rule_from_pretty_json():
    """Against the real pretty-printed shape, the extractor yields the
    block rule's id only."""
    out = _run(_extract_unban_id_program(), _PRETTY_RESPONSE)
    ids = out.split()
    assert ids == ["BLOCK_RULE_ID"], (
        f"expected only the block rule id; got {ids!r}"
    )


def test_unban_extractor_ignores_whitelist_and_scope_ids():
    """It must not target a legitimate whitelist/allow rule for the same
    IP, nor the nested scope.id (the greedy-sed trap)."""
    out = _run(_extract_unban_id_program(), _PRETTY_RESPONSE)
    assert "WHITELIST_RULE_ID" not in out, "must not delete a whitelist rule"
    assert "SCOPE_ID_X" not in out, "must not target the nested scope.id"


def test_unban_extractor_empty_when_no_block_rule():
    """No block rule → empty output → the for-loop deletes nothing
    (silent no-op, matching the 'already gone' path)."""
    assert _run(_extract_unban_id_program(), _EMPTY_RESPONSE) == ""


def test_actionunban_is_not_compact_only_sed():
    """Guard the specific regression: the brittle compact-only
    ``"id":"`` sed extraction must be gone from actionunban."""
    text = _ACTION_CONFIG.read_text()
    # the exact fragile fragment that only matches space-less JSON
    assert r's/.*"id":"\([^"]*\)".*/\1/p' not in text, (
        "actionunban still uses the compact-only sed that cannot parse "
        "Cloudflare's pretty-printed JSON"
    )
