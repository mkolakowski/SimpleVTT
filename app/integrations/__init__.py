"""Outbound integrations with third-party APIs.

Each module wraps one external service (Cloudflare today; future
adds land here too). Per CLAUDE.md's "Third-party APIs must be
Docker Compose services" rule, every integration is paired with a
mock service in docker-compose.yml so the integration can be
exercised in dev without burning real API quota.
"""
