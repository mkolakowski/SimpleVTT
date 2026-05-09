#!/usr/bin/env python3
"""
Download Open5e SRD data and cache it locally.

Usage:
    python scripts/sync_open5e.py

Data is saved to app/data/open5e/*.json.
After running, set LOCAL_OPEN5E=true in your environment to enable fast local
lookups instead of hitting api.open5e.com on every request.
"""
import json
import pathlib
import sys
import urllib.request

DATA_DIR = pathlib.Path(__file__).parent.parent / "app" / "data" / "open5e"

ENDPOINTS: dict[str, str] = {
    "classes":    "https://api.open5e.com/v1/classes/?limit=100",
    "subclasses": "https://api.open5e.com/v1/subclasses/?limit=100",
    "races":      "https://api.open5e.com/v1/races/?limit=100",
    "spells":     "https://api.open5e.com/v1/spells/?limit=100",
    "conditions": "https://api.open5e.com/v1/conditions/?limit=50",
}


def fetch_all(start_url: str) -> list:
    """Fetch all pages from a paginated Open5e endpoint."""
    results: list = []
    url: str | None = start_url
    while url:
        print(f"    GET {url}", end="", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        batch = data.get("results", [])
        results.extend(batch)
        print(f"  → {len(batch)} records (total {len(results)})")
        url = data.get("next")
    return results


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving data to: {DATA_DIR}\n")

    failed: list[str] = []
    counts: dict[str, int] = {}
    for name, url in ENDPOINTS.items():
        print(f"Fetching {name}…")
        try:
            items = fetch_all(url)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            failed.append(name)
            continue
        path = DATA_DIR / f"{name}.json"
        path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        counts[name] = len(items)
        print(f"  Saved {len(items)} {name} → {path.name}\n")

    if counts:
        import datetime
        manifest = {
            "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "counts": counts,
        }
        manifest_path = DATA_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"  Manifest written → {manifest_path.name}\n")

    if failed:
        print(f"WARNING: Failed to sync: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)

    print("Done!")
    print("To enable local lookups, set:  LOCAL_OPEN5E=true")


if __name__ == "__main__":
    main()
