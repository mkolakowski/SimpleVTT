# Admin Center — TOTP MFA + env recovery code (design plan)

**Status:** ⚪ proposed (design only — not yet implemented).
**Scope:** the standalone Admin Center service (`app/admin_center/`,
port 8015). Does **not** touch the main app's login.

This plan adds an **optional, env-gated TOTP second factor** to the
Admin Center login (v2.485.3 password page + v2.485.4 brute-force
throttle), plus an **env-set recovery code** for the TOTP-loss case.

---

## 1 — Goals & non-goals

**Goals**

- TOTP (RFC 6238, 30s / 6-digit, SHA-1 — what Google Authenticator /
  Aegis / 1Password generate) as a second factor after the password.
- Strictly **opt-in**: off by default; one env flag turns it on.
- A **recovery code** set in the environment so an operator who loses
  their authenticator can still get in — but with a hard safety
  property: **a blank recovery code accepts nothing** (see §4).
- Keep the admin center **stateless + non-root + single-credential**
  (no user DB of its own); secrets come from the environment, exactly
  like `ADMIN_CENTER_USER` / `ADMIN_CENTER_PASS`.

**Non-goals**

- Per-user MFA / multiple operators (the admin center is single-
  credential by design).
- WebAuthn / hardware keys (possible future follow-up).
- SMS / email codes (no mail transport in the admin center).
- Changing the main app's auth.

---

## 2 — New environment variables

| Env var | Default | Effect |
|---|---|---|
| `ADMIN_CENTER_MFA_ENABLED` | `false` | Master switch. When false the login is password-only (today's behavior). |
| `ADMIN_CENTER_TOTP_SECRET` | _(blank)_ | Base32 TOTP shared secret. Required when MFA is enabled; if enabled with a blank secret the service **fails closed** (see §5). |
| `ADMIN_CENTER_RECOVERY_CODE` | _(blank)_ | A single recovery code accepted in place of a TOTP code. **Blank = no code is ever accepted** (§4). |

Provisioning the secret (operator runs once):

```
python -c "import secrets,base64; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip('='))"
```

Then add it to an authenticator app via the `otpauth://` URI the
login page renders as a QR on first setup (see §6).

---

## 3 — Login flow

```
POST /login (username + password)
  ├─ throttle / credential check  (unchanged, v2.485.3/.4)
  └─ on success:
       ├─ MFA disabled → set session admin_authed=True → dashboard
       └─ MFA enabled  → set session mfa_pending=True → 303 /login/mfa
GET  /login/mfa   → code-entry form (only reachable with mfa_pending)
POST /login/mfa   (code)
       ├─ valid TOTP (current ±1 step skew) → admin_authed=True, clear
       │  mfa_pending → dashboard
       ├─ valid recovery code (§4)          → same, + log a warning +
       │  one-shot consume (see §4)
       └─ invalid → feed the brute-force throttle (login_guard),
          re-render with error
```

Session is only marked `admin_authed` **after** the second factor;
`mfa_pending` alone grants nothing (the auth middleware checks
`admin_authed`).

---

## 4 — Recovery code (the safety property)

The operator's explicit requirement: *leave blank by default, and the
default must not accept any code unless one is set.*

Rules:

1. `ADMIN_CENTER_RECOVERY_CODE` is blank by default.
2. The check is, in this exact order:
   ```python
   configured = os.environ.get("ADMIN_CENTER_RECOVERY_CODE", "").strip()
   if not configured:
       return False                      # blank → NOTHING is accepted
   return secrets.compare_digest(submitted.strip(), configured)
   ```
   A blank/whitespace config can never match — even a blank submitted
   code is rejected before the compare. This closes the "empty == empty"
   bypass.
3. Constant-time compare (`secrets.compare_digest`) so the code can't
   be timed out character-by-character.
4. **One-shot:** once a recovery code logs in successfully, log a
   loud `WARNING` ("recovery code used — rotate it") and set an
   in-process "recovery used" flag so the same process won't accept it
   again until the operator rotates the env var + restarts. (In-process
   only, matching the rest of the admin center's best-effort state;
   documented as such.)
5. The recovery code path still passes the **password** first — it
   only substitutes for the TOTP step, never for the password.

---

## 5 — Fail-closed when misconfigured

If `ADMIN_CENTER_MFA_ENABLED=true` but `ADMIN_CENTER_TOTP_SECRET` is
blank/invalid, the service must **fail closed**: the login page shows
"MFA is enabled but no TOTP secret is configured — set
`ADMIN_CENTER_TOTP_SECRET`" and refuses all logins (rather than
silently dropping back to password-only, which would be a downgrade
attack surface). The recovery code alone does **not** satisfy a
missing TOTP secret — MFA-on with no secret is a config error, not a
recovery scenario.

---

## 6 — TOTP implementation notes

- **Dependency:** prefer `pyotp` (tiny, well-audited) for the TOTP
  verify + the `otpauth://` provisioning URI. Alternative: a ~30-line
  stdlib `hmac`/`struct`/`base64` implementation if we want zero new
  deps. Decision deferred to implementation; `pyotp` is the default
  recommendation.
- **Verify:** `totp.verify(code, valid_window=1)` to tolerate ±1 step
  (30s) of clock skew. The admin-center container should run the same
  TZ as the host; TOTP is UTC-based so TZ doesn't matter, but clock
  drift does — note NTP in the wiki.
- **Provisioning QR:** on first setup (a `GET /login/mfa/setup` page,
  shown only before the first successful TOTP, or gated behind a
  one-time env flag) render the `otpauth://totp/SimpleVTT%20Admin:...`
  URI as a QR (client-side via a tiny QR lib, or a server-rendered
  SVG). The secret is never shown in logs.
- **No secret in the session/cookie.** The secret lives only in the
  env; the session stores booleans (`mfa_pending`, `admin_authed`).

---

## 7 — Module / file plan

| File | Change |
|---|---|
| `app/admin_center/mfa.py` (new) | Pure helpers: `mfa_enabled()`, `totp_configured()`, `verify_totp(code, *, now)`, `recovery_code_accepts(submitted)` (the §4 logic), `provisioning_uri()`. Stdlib + (optional) pyotp; unit-testable with an injected clock/secret. |
| `app/admin_center/main.py` | Branch the login flow (§3): `mfa_pending` session step, `GET/POST /login/mfa`, fail-closed (§5). Feed `login_guard` on bad codes. |
| `app/admin_center/templates/mfa.html` (new) | Code-entry form (44px targets, error + "use recovery code" affordance). |
| `docker-compose.yml` / `.env.example` | The three env vars (§2), all defaulting to off/blank. |
| `docs/wiki/admin-center.md` | "Two-factor authentication" section: enable steps, provisioning, recovery-code caveat (blank = disabled), NTP note. |

---

## 8 — Harness tests (when built)

Pure unit tests on `app/admin_center/mfa.py` (host-side, injected
clock/secret — same pattern as `login_guard` / `dns_lookup`):

- TOTP: a known secret + fixed timestamp verifies the expected code;
  ±1 window tolerated; 2 windows away rejected.
- **Recovery code, blank → rejects everything** (including a blank
  submission) — the headline safety property.
- Recovery code set → exact match accepted (constant-time), mismatch
  rejected; one-shot consume flips to rejected.
- `mfa_enabled()` / fail-closed: enabled + blank secret → "configured"
  is False → login refused.

Live tests: MFA-disabled (default) login still works end-to-end;
MFA-enabled stack (env set in a test override) → password alone lands
on `/login/mfa`, a valid code completes login, a bad code re-prompts.

---

## 9 — Rollout

1. Land `mfa.py` + unit tests (no wiring) — pure, safe.
2. Wire the login flow + templates behind `ADMIN_CENTER_MFA_ENABLED`
   (default off → zero behavior change for existing deploys).
3. Provisioning QR page.
4. Wiki "Two-factor authentication" section + `.env.example`.
5. Optional follow-up: WebAuthn / multiple operators.

Default-off at every step means this ships without affecting any
current Admin Center deployment until an operator opts in.
