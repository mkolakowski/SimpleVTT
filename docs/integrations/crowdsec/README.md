# CrowdSec integration for SimpleVTT

Reference parser + scenarios for wiring CrowdSec to SimpleVTT's
canonical audit-log lines (`app/audit_log.py`). Same line shape
the fail2ban filter at `../fail2ban/filter.d/simplevtt-auth.conf`
consumes — pick whichever engine fits your deployment.

## Why CrowdSec over fail2ban?

- **Native Cloudflare bouncer**: `cs-cloudflare-blocker` translates
  CrowdSec decisions directly into Cloudflare IP Access Rules via
  the same API SimpleVTT's `/admin/cloudflare/ban_ip` endpoint
  uses. Wire it once and your CrowdSec scenarios automatically
  enforce at the Cloudflare edge with no host-side iptables.
- **Community signal sharing**: CrowdSec's community feed propagates
  banned-IP intelligence across deployments. SimpleVTT operators
  who opt in benefit from threat data observed at unrelated sites.
- **YAML scenarios**: more expressive than fail2ban regex filters
  for multi-event patterns (e.g. "10 different paths probed by one
  IP" or "admin minting a flood of magic links").

Run fail2ban instead if you're on a small host without a
Cloudflare bouncer and want the simplest possible setup.

## Install

```bash
# 1. Parser
sudo cp parsers/s01-parse/simplevtt.yaml \
    /etc/crowdsec/parsers/s01-parse/simplevtt.yaml

# 2. Scenarios
sudo cp scenarios/*.yaml /etc/crowdsec/scenarios/

# 3. Acquisition — point CrowdSec at the SimpleVTT log source
sudo tee /etc/crowdsec/acquis.d/simplevtt.yaml <<'EOF'
source: file
filenames:
  - /var/log/simplevtt/app.log     # adjust to your setup
labels:
  type: simplevtt-audit
EOF

# Common alternatives for the log source:
#   - docker logs: /var/lib/docker/containers/<id>/<id>-json.log
#   - journald:    use the `journald` source instead of `file`

# 4. Reload
sudo systemctl reload crowdsec

# 5. Verify the parser picked up the file
sudo cscli explain --file /var/log/simplevtt/app.log --type simplevtt-audit
```

## Available scenarios

| Scenario | Trip threshold | Ban duration | Labels |
|---|---|---|---|
| `simplevtt/auth-bruteforce` | 5× `auth.login_failed` in 5 min | 5 min | `attack.credential-access` |
| `simplevtt/magic-link-bruteforce` | 5× `demo_magic_link.verify_rejected reason=signature` in 5 min | 5 min | `attack.credential-access` |
| `simplevtt/magic-link-replay` | 1× `demo_magic_link.verify_rejected reason=replay` | 24 h | `attack.credential-access` |
| `simplevtt/api-probe` | 10× `api.unauthorized` or `api.forbidden` in 10 min | 5 min | `attack.reconnaissance` |
| `simplevtt/admin-mint-flood` | 10× `demo_magic_link.mint_ok` in 5 min | 1 h | `attack.privilege-escalation` |

(Blackhole durations are the same on the SimpleVTT-side. CrowdSec
decision durations — i.e. how long the IP stays in the
bouncer-enforced ban list — are set by the bouncer config.)

## Wiring to Cloudflare

Install the CrowdSec → Cloudflare bouncer separately:

```bash
sudo apt install crowdsec-cloudflare-blocker
sudo cs-cloudflare-blocker -g <your-cloudflare-api-token> \
    --zone-name <your-zone-name>
```

The bouncer reads CrowdSec decisions and translates them to
Cloudflare IP Access Rules via the same API endpoint SimpleVTT's
`/admin/cloudflare/ban_ip` uses (so an operator running both gets
a clean detect-and-enforce pipeline without rebuilding it).

## Manual smoke test (no compose override)

```bash
# Replay a synthetic auth-bruteforce stream into the test parser:
for i in {1..6}; do
  echo "2026-06-18 12:34:5${i},000 WARNING simplevtt.audit: \
auth.login_failed ip=203.0.113.42 ua=\"curl/8.0\" \
username=victim@example.com" | \
    sudo cscli explain --type simplevtt-audit -
done
```

A successful run prints the parsed event subtype, source IP, and
which scenarios it fed. After the 5th line the
`simplevtt/auth-bruteforce` scenario should report "alert
generated."

## Filed for Phase 2B

- **Compose-side smoke test** — `docker-compose.crowdsec.yml`
  override + harness test that brings up a real CrowdSec container,
  replays synthetic events, and asserts the scenarios fire via
  `cscli decisions list`. The compose override file is partially
  templated below; the harness test waits on the CrowdSec image
  being reliably available from Docker Hub.
