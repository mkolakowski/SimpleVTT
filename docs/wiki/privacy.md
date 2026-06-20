# Privacy Policy

This page is the **GDPR-compliant privacy notice template** for
SimpleVTT. It is structured to satisfy Articles 12–14 of the EU
General Data Protection Regulation (transparency at collection)
and enumerate the rights in Articles 15–22.

> **Operator action required before publishing.** Fill in the
> placeholders in [Section 1 — Controller and contact](#1--controller-and-contact)
> before publishing this page to your users. The rest of the
> page is pre-filled based on what SimpleVTT actually does;
> values that vary per-deploy are clearly marked. Have counsel
> review for your specific jurisdiction — this template
> satisfies the GDPR's transparency requirements but isn't a
> substitute for legal advice on your specific deployment.

---

## 1 — Controller and contact

Under GDPR, the **controller** is the natural or legal person
who determines the purposes and means of processing personal
data. **The operator running this SimpleVTT instance is the
controller**, not the SimpleVTT project upstream.

**Controller:** _[Your organization or individual name]_
**Registered address:** _[Your registered postal address]_
**Email for privacy requests:** _[privacy@your-domain.example]_
**Data Protection Officer (DPO):** _[Name + contact, or "Not
appointed — this deployment does not meet the Article 37
thresholds"]_
**Supervisory authority:** _[The supervisory authority for your
EU member state. Examples: ICO (UK — post-Brexit equivalent
regime), CNIL (France), BfDI (Germany), Garante (Italy). If you
are not in the EU/UK but process EU resident data, name your
representative under Article 27.]_

---

## 2 — What data we process

### 2.1 — Account data

| Field | Purpose |
|---|---|
| Email address | Authentication, contact channel |
| Password hash (bcrypt) | Authentication |
| Display name | Identification in shared sessions |
| Color | UI personalization |
| Role (admin / user) | Authorization |
| Google SSO opaque uid (optional) | Authentication via Google |

**Legal basis:** Article 6(1)(b) — performance of a contract
(you can't use SimpleVTT without an account, and we can't
authenticate you without these fields). The Google SSO uid is
6(1)(a) — consent, since you choose Google as your sign-in
method.

**Retention:** for the life of the account + 30 days after
account deletion (the buffer covers operator backup-rotation
windows so a "delete me" request takes effect even after a
backup restore). Plaintext passwords are **never** stored or
logged.

### 2.2 — Session data

A signed cookie carrying `user_id` (integer) issued by
Starlette's `SessionMiddleware` using `APP_SECRET_KEY`. The
cookie is signed but not encrypted; without `APP_SECRET_KEY`
nobody can forge a valid signature.

**Legal basis:** Article 6(1)(b) — performance of a contract
(authentication requires a session). The cookie is
"strictly necessary" under ePrivacy / PECR; no consent banner is
required for its use.

**Retention:** browser session by default (cleared when the
user closes their browser).

### 2.3 — Audit log events (security log)

SimpleVTT writes a structured text log for every event
relevant to detecting attacks. The log lands at
`/var/log/simplevtt/audit.log` (rotated at 10 MB × 5 backups,
~50 MB total) and on the app's stdout.

Catalog of events:

| Event tag | Triggered by | Personal data recorded |
|---|---|---|
| `auth.login_ok` | Successful sign-in | `user_id`, IP, User-Agent |
| `auth.login_failed` | Bad password / unknown email | typed username, IP, User-Agent |
| `auth.signup_failed` | Registration rejected | reason, IP, User-Agent |
| `demo_magic_link.mint_ok` | Admin minted a magic link | admin `user_id`, link `sub`+`jti`, IP, UA |
| `demo_magic_link.verify_ok` | Magic-link login succeeded | link `sub`+`jti`, IP, UA |
| `demo_magic_link.verify_rejected` | Magic-link refused | reason, IP, UA |
| `api.unauthorized` | 401 on a protected endpoint | path, IP, UA |
| `api.forbidden` | 403 on a protected endpoint | path, IP, UA |
| `api.not_found` *(v2.477.0)* | 404 on any path | path, IP, UA |
| `admin.<action>` | Admin destructive action | admin `user_id`, target id, IP, UA |
| `cloudflare.ban_ok` / `cloudflare.unban_ok` | Cloudflare API ban/unban | banned IP, admin `user_id`, IP, UA |

**Legal basis:** Article 6(1)(f) — legitimate interest in
network security, fraud prevention, and abuse detection
(Recital 49 explicitly recognizes this purpose). The balancing
test favors processing because (a) the data is technically
necessary for the stated purpose, (b) we don't enrich the data
with marketing or behavioral profiles, and (c) we minimize the
data captured (no request bodies, no auth tokens, no
passwords).

**Retention:**
- Events that lead to a ban: **1 year** from the ban event date,
  to support investigation + appeal.
- Events that do not lead to a ban: **90 days**, to support
  burst-detection windows (replay attacks, scanner waves).

If your operator deployment runs without log rotation, the
default RotatingFileHandler caps the file at ~50 MB total
(10 MB × 5 backups). Operators in jurisdictions requiring
shorter retention should configure host-side log rotation
or set `AUDIT_LOG_PATH=` (empty) to disable the file handler
entirely.

### 2.4 — Game state

Campaigns, characters, sheets, battle state, chat messages, and
roll history.

**Legal basis:** Article 6(1)(b) — performance of a contract
(the service IS the game state).

**Retention:** indefinite while the account is active; deleted
30 days after account deletion (same buffer as Section 2.1).

### 2.5 — Uploaded assets

Map images, token images, audio clips, and thumbnails uploaded
by users.

**Legal basis:** Article 6(1)(b).

**Retention:** indefinite while the campaign exists. Deleting
the campaign deletes the database-side metadata; orphaned
binary files are pruned during the operator's quarterly volume
sweep.

### 2.6 — Database backups

Daily and weekly `pg_dump` snapshots in the `backup_data` volume
(7 daily + 4 weekly = ~5 weeks of history with default config).

**Legal basis:** Article 6(1)(f) — legitimate interest in
business continuity + disaster recovery.

**Retention:** governed by the operator's `BACKUP_CRON` /
`KEEP_DAILY` / `KEEP_WEEKLY` env vars. Default: 7 daily + 4
weekly, rotating.

---

## 3 — Recipients of personal data

### 3.1 — Inside the SimpleVTT operator's infrastructure

Data is processed by:
- The SimpleVTT application container (uvicorn worker as
  unprivileged user `appuser`, v2.474.0+).
- The PostgreSQL container.
- The `backup` container (runs `pg_dump` on cron).
- Optionally, the `fail2ban` container (reads the audit log;
  only when the `--profile fail2ban` is enabled by the
  operator).

These run on the operator's infrastructure under the
operator's control.

### 3.2 — Third-party processors / sub-processors

| Recipient | Purpose | Country | Gate |
|---|---|---|---|
| Google LLC | Sign-in via OAuth (Google SSO) | United States | Only if operator sets `GOOGLE_SSO_ENABLED=true` AND a user chooses Google as their sign-in method (Article 6(1)(a) — consent) |
| Cloudflare, Inc. | Edge-side IP ban list management | United States | Only if operator sets `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true`. Data shared: banned IP + a free-form "fail2ban" or admin-id note (no user data, no request payloads) |

SimpleVTT does **not** use analytics services, advertising
networks, A/B-test SDKs, or any other third-party SDKs in the
browser.

### 3.3 — International transfers

Where third-party processors (Google, Cloudflare) are based
outside the European Economic Area, transfers happen under the
European Commission's adequacy decisions or the
Standard Contractual Clauses (SCCs):

- **Google LLC** (US): Data Privacy Framework participant +
  SCCs.
- **Cloudflare, Inc.** (US): Data Privacy Framework participant
  + SCCs.

Operators relying on either integration are responsible for
confirming the current status of these mechanisms; both vendors
publish their certifications on their respective trust pages.

---

## 4 — Automated decision-making (Article 22)

SimpleVTT runs **one** automated decision process that produces
legal or similarly significant effects on data subjects: the
fail2ban-driven IP ban.

**How it works:**
- The audit log records IPs that hit a failure threshold
  (default: 5 failed logins in 5 min, or 20 distinct 404s in
  5 min).
- The fail2ban container reads the log and inserts the IP into
  a ban list (in-container iptables, ipset on the host, or a
  Cloudflare access rule, per operator choice).
- The ban expires automatically (default: 1 hour for auth,
  6 hours for scanner).

**Right to appeal:** users banned in error can contact the
operator at the email in Section 1 to request an unban. The
operator runs:

```bash
docker compose --profile fail2ban exec fail2ban \
    fail2ban-client unban <ip>
```

If the ban landed at the Cloudflare edge, the operator also
removes the corresponding access rule via the Cloudflare
dashboard or the in-app admin portal.

**Why this is the only automated decision:** SimpleVTT does not
profile users for behavioral analytics, credit scoring, or any
other purpose. The ban decision is narrowly scoped to source IP
+ recent log activity.

---

## 5 — Your rights as a data subject

Under the GDPR you have the rights enumerated below. To
exercise any of them, contact the operator at the email in
Section 1. We will respond within **one month** of receipt
(Article 12(3)), extendable by two further months for complex
requests with notice to you.

### 5.1 — Right of access (Article 15)

You can request a copy of all personal data we hold about you.
The operator runs the following against the database (where
`<your-email>` is your sign-in email):

```sql
SELECT id, email, display_name, role, created_at FROM users
WHERE email = '<your-email>';

SELECT c.id, c.name FROM campaigns c
JOIN campaign_memberships m ON m.campaign_id = c.id
JOIN users u ON u.id = m.user_id
WHERE u.email = '<your-email>';

SELECT id, name, campaign_id FROM characters
WHERE owner_user_id = (
    SELECT id FROM users WHERE email = '<your-email>'
);
```

For audit-log entries about you, the operator runs:

```bash
docker compose exec app \
    grep "user_id=<your-user-id>" /var/log/simplevtt/audit.log
```

The result is delivered to you as a machine-readable export
(JSON or CSV).

> **Operator follow-on (filed in TODO):** add a `/api/users/me/export`
> endpoint so a logged-in user can self-serve this request. See
> the TODO "GDPR Article 15/20 user data export endpoint."

### 5.2 — Right to rectification (Article 16)

You can correct inaccurate personal data. Display name + color
are user-editable via the in-app settings page. Email + password
changes also flow through the settings page. For other fields,
contact the operator.

### 5.3 — Right to erasure / "right to be forgotten" (Article 17)

You can request deletion of your account. The operator runs a
user-delete from the admin portal; this cascades to your
campaigns (if you own them), characters, sheets, chat messages,
and roll history.

**What does NOT auto-delete:**
- **Audit-log entries about you** are retained for the periods
  in Section 2.3 (90 days / 1 year for ban-relevant). This is
  permitted under Article 17(3)(b) — exercising the legal right
  to defend against security claims — and Article 17(3)(e) —
  legal claims. Operators may grep + redact the log on request
  but are not obliged to.
- **Database backups** that include your data are retained per
  the operator's `BACKUP_CRON` config. Backups taken before your
  deletion request will roll out of the retention window per
  policy. Operators do not selectively scrub historical
  backups.

> **Operator follow-on (filed in TODO):** add an admin-driven
> audit-log scrub command that pseudonymizes `user_id` values
> for deleted users while preserving the security-relevant
> structure of the log.

### 5.4 — Right to restriction of processing (Article 18)

You can request that we stop processing your personal data
beyond what's strictly necessary to fulfill your contract (i.e.,
beyond what's needed to keep your account functioning). Contact
the operator. SimpleVTT does not run optional processing
(analytics, marketing) by default, so the practical effect is
usually limited.

### 5.5 — Right to data portability (Article 20)

You can request your personal data in a machine-readable format.
The export from Section 5.1 satisfies this.

### 5.6 — Right to object (Article 21)

You can object to processing based on legitimate interests
(Article 6(1)(f) — primarily the audit log). The operator
assesses whether their interest in security overrides yours;
in most cases for security logs the answer is yes (Recital 49),
but you have the right to a documented response.

### 5.7 — Right to withdraw consent (Article 7(3))

Where the processing legal basis is consent (Section 3.2's
Google SSO uid), you can withdraw consent at any time by
deleting your account or unlinking Google SSO from the
settings page. Withdrawal does not affect the lawfulness of
processing before the withdrawal.

### 5.8 — Right to lodge a complaint (Article 77)

You have the right to lodge a complaint with the supervisory
authority listed in Section 1. You may also lodge with the
authority for your habitual residence, place of work, or place
of the alleged infringement.

---

## 6 — Data we deliberately don't collect

- **No per-request access log (by default).** SimpleVTT does
  **not** log every HTTP request out of the box. Only
  banning-relevant events (Section 2.3) get logged. An operator
  who wants full visitor accounting behind a Cloudflare Tunnel
  can opt in with `VISITOR_REQUEST_LOG_ENABLED=true`
  (Section 10), which emits a `visitor.request` audit event per
  request (path, method, status, response time, IP, user agent).
  It is **OFF by default** for privacy + log-volume reasons and
  additionally requires `TRUSTED_PROXY_HOPS>=1` so the recorded
  IP is the real visitor rather than the tunnel's internal
  address. Enabling it is a material change to data processing —
  see Section 11.
- **No browser fingerprinting.** No canvas / font / WebGL probes.
  No third-party trackers.
- **No password content.** Plaintext passwords are never
  logged, even on failure paths.
- **No marketing PII on `auth.login_ok`.** Successful logins
  record `user_id`, not email — so a log breach can't be
  cross-referenced to email addresses without database access.

---

## 7 — Security measures

Technical and organizational measures (Article 32):

- **Encryption in transit.** SimpleVTT is served over HTTPS
  in production (operator's reverse proxy or Cloudflare edge).
- **Password hashing.** bcrypt with a per-password salt
  (`passlib`).
- **Non-root container.** The app container drops from root to
  unprivileged `appuser` (uid 999, no login shell) via gosu at
  startup (v2.474.0+). A container escape lands as `appuser`,
  not root.
- **fail2ban-driven IP banning.** See Section 4.
- **Backups + restore-tested at operator discretion.**
- **Access controls.** Database access requires
  `POSTGRES_PASSWORD`; admin role gates destructive actions in
  the application (delete user, delete campaign, ban IP); every
  admin action is recorded in the audit log per Section 2.3.

---

## 8 — Data breach notification (Article 33–34)

If we discover a personal data breach we will:

1. **Within 72 hours of becoming aware**, notify the supervisory
   authority listed in Section 1 (Article 33), unless the
   breach is unlikely to result in a risk to your rights and
   freedoms.
2. **Without undue delay**, notify affected data subjects
   (Article 34) when the breach is likely to result in a high
   risk to your rights and freedoms.

The operator's breach response runbook (recommended:
[Section X of the operator's incident-response plan]) covers
detection, containment, scope assessment, notification, and
remediation steps.

---

## 9 — Children

GDPR Article 8 sets the threshold for valid consent for
"information society services" at 16 years (member states may
lower to 13–16). Operators serving users in EEA member states
should:

- Configure account creation to verify age, OR
- Require parental consent for under-threshold users, OR
- Refuse service to users under the relevant threshold.

The SimpleVTT default does not perform age verification.
Operators planning to serve minors are responsible for adding
this gate (e.g., a "must be 16 or older" checkbox at signup, or
operator-managed account provisioning that screens age out of
band).

---

## 10 — Operator-controlled privacy knobs

Every privacy-relevant default is a single environment variable
on the app container. Operators can override any of these to
match their threat model + jurisdiction.

| Env var | Default | Effect |
|---|---|---|
| `AUDIT_LOG_PATH` | `/var/log/simplevtt/audit.log` | File path for the audit log tee. Set to empty string to disable file logging (stdout-only). |
| `TRUSTED_PROXY_HOPS` | `0` | Trust depth for `X-Forwarded-For`. Set `1` behind one reverse proxy, etc. **Required for accurate IP attribution behind Cloudflare / nginx.** |
| `VISITOR_REQUEST_LOG_ENABLED` | `false` | Opt into a per-request `visitor.request` audit event (full visitor accounting: path, method, status, response time, IP, UA). OFF by default; also requires `TRUSTED_PROXY_HOPS>=1`. Enabling it is a material change to data processing — disclose it in your published policy. |
| `APP_ALLOW_LOCAL_REGISTRATION` | `true` | Whether anyone can self-register. `false` to require operator-managed account creation. |
| `GOOGLE_SSO_ENABLED` | `false` | Whether Google SSO is offered. Disable to remove Google as a recipient (Section 3.2). |
| `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED` | `false` | Whether the in-app Cloudflare ban + fail2ban Cloudflare bouncer can talk to the Cloudflare API. Disable to remove Cloudflare as a recipient. |
| `BACKUP_CRON` / `KEEP_DAILY` / `KEEP_WEEKLY` | `0 3 * * *` / `7` / `4` | Backup schedule + retention. Set `KEEP_*=0` to disable backups entirely. |
| `FAIL2BAN_LOGIN_BANTIME` / `FAIL2BAN_SCANNER_BANTIME` | `1h` / `6h` | Automated decision durations (Article 22 relevant). |

For the full set, see [`.env.example`](/wiki/doc/changelog) at
the repo root.

---

## 11 — Changes to this policy

This policy is versioned with the SimpleVTT release. Material
changes to data processing (new event tags, new third-party
processors, expanded retention) ship in CHANGELOG entries and
this page is updated in the same release.

Operators are responsible for surfacing material changes to
their users. A common pattern is to email registered users when
the policy is updated.

---

## 12 — Effective date

This policy applies as published. Operators should fill in
**Effective date:** _[YYYY-MM-DD when this version was
published]_ before going live.

---

## See also

- [fail2ban deployment guide](/wiki/fail2ban-deployment) — the
  audit log's primary consumer.
- [fail2ban / CrowdSec integration plan](/wiki/doc/plan-fail2ban-crowdsec-integration)
  — design doc for the audit log line shape + threat model.
- [Cloudflare edge-banning plan](/wiki/doc/plan-cloudflare-edge-banning)
  — the in-app ban button's design.
- [Demo magic-link plan](/wiki/doc/plan-demo-magic-link) — the
  passwordless login flow's privacy model.
