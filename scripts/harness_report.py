#!/usr/bin/env python3
"""Summarize a pytest JUnit XML: counts, slowest tests, and failures.

Prints a human summary and (with --json) writes a compact JSON the admin
"Tests" dashboard reads to chart pass/fail + per-test timing. Pure stdlib.

Usage:
    python3 scripts/harness_report.py test-results/latest.xml
    python3 scripts/harness_report.py <xml> --json test-results/latest.json
"""
from __future__ import annotations

import argparse
import json
import os
import xml.etree.ElementTree as ET


def _status(tc: ET.Element) -> str:
    if tc.find("failure") is not None:
        return "failed"
    if tc.find("error") is not None:
        return "error"
    if tc.find("skipped") is not None:
        return "skipped"
    return "passed"


def parse(xml_path: str) -> dict:
    root = ET.parse(xml_path).getroot()
    # JUnit root is <testsuites> or a single <testsuite>.
    suites = root.iter("testsuite")
    cases: list[dict] = []
    for suite in suites:
        for tc in suite.iter("testcase"):
            st = _status(tc)
            msg = ""
            node = tc.find("failure") if st == "failed" else tc.find("error")
            if node is not None:
                msg = (node.get("message") or "").strip().splitlines()[0][:200] \
                    if (node.get("message")) else ""
            cases.append({
                "classname": tc.get("classname", ""),
                "name": tc.get("name", ""),
                "time": float(tc.get("time") or 0.0),
                "status": st,
                "message": msg,
            })
    counts = {k: sum(1 for c in cases if c["status"] == k)
              for k in ("passed", "failed", "error", "skipped")}
    total_time = round(sum(c["time"] for c in cases), 1)
    return {
        "source": os.path.basename(xml_path),
        "total": len(cases),
        "counts": counts,
        "duration_s": total_time,
        "slowest": sorted(cases, key=lambda c: c["time"], reverse=True)[:30],
        "failures": [c for c in cases if c["status"] in ("failed", "error")],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml", nargs="?", default="test-results/latest.xml")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    report = parse(args.xml)
    c = report["counts"]
    print(f"\n== Harness summary: {report['total']} tests in "
          f"{report['duration_s']}s — {c['passed']} passed, {c['failed']} failed, "
          f"{c['error']} errored, {c['skipped']} skipped ==")
    print("\nSlowest 15:")
    for tc in report["slowest"][:15]:
        print(f"  {tc['time']:7.2f}s  [{tc['status']:6}] "
              f"{tc['classname']}::{tc['name']}")
    if report["failures"]:
        print(f"\nFailures / errors ({len(report['failures'])}):")
        for tc in report["failures"][:60]:
            print(f"  [{tc['status']:6}] {tc['classname']}::{tc['name']}"
                  + (f"  — {tc['message']}" if tc["message"] else ""))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
