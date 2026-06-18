# Cloudflare API wiremock fixture

Canned `IP Access Rules` API responses for dev + integration testing
of `app/integrations/cloudflare.py`. Run the wiremock service from the
repo root with the `dev` profile:

```bash
docker compose --profile dev up cloudflare-mock
```

Then point the SimpleVTT app at it:

```env
CLOUDFLARE_API_TOKEN=dev-fake-token
CLOUDFLARE_ZONE_ID=dev-fake-zone
CLOUDFLARE_API_BASE_URL=http://cloudflare-mock:8080/client/v4
SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true
```

(From the host machine, the wiremock is also reachable at
`http://localhost:8014` since the container port maps `8014→8080`.)

## Mappings

Each file under `mappings/` is a wiremock stub mapping for one
Cloudflare API endpoint:

- `post-access-rule.json` — `POST /client/v4/zones/<id>/firewall/access_rules/rules`
  returns 200 with a stub rule id.
- `delete-access-rule.json` — `DELETE .../rules/<rule_id>` returns 200.
- `list-access-rules.json` — `GET .../rules` returns 200 with one rule.

The fixtures are **stateless** by design — wiremock doesn't track
"did you POST first" before the GET returns a rule. SimpleVTT's
`admin_audit_log` table is the local source of truth for what we've
asked Cloudflare to ban; the upstream list is observational.

## Adding error-path scenarios

For tests that need to exercise the failure paths (5xx upstream,
malformed body, etc.), add a stub with a `priority` field — lower
priority wins ties. Example:

```json
{
  "priority": 1,
  "request": {
    "method": "POST",
    "urlPathPattern": "/client/v4/zones/[^/]+/firewall/access_rules/rules",
    "headers": {"X-Simulate-Error": {"equalTo": "upstream_500"}}
  },
  "response": {"status": 500, "body": "internal server error"}
}
```

Then add the header in the test client to flip into the error path.
