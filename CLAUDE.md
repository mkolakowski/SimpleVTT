# SimpleVTT — Claude Code guidelines

## Third-party APIs must be Docker Compose services

When integrating any external API or data service, add it as a named service in
`docker-compose.yml` rather than calling a public endpoint directly at request
time. This keeps every dependency on the internal Docker network, works offline,
and removes runtime internet calls from the hot path.

**Pattern to follow for every new API:**

1. Add a service block in `docker-compose.yml` with a `healthcheck`.
2. Add the internal base URL as an env var in the `app` service
   (e.g. `MY_API_BASE_URL: http://myapi:port/v1`).
3. Add the env var (commented out) to `.env.example` with a note that
   docker-compose sets it automatically.
4. Read the env var at module level in the relevant route file with a sensible
   public-internet default so the app still works outside Docker:
   ```python
   _MY_API_BASE = os.getenv("MY_API_BASE_URL", "https://api.example.com/v1").rstrip("/")
   ```
5. Use that variable everywhere instead of a hardcoded URL.
