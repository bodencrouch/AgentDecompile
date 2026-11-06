#!/usr/bin/env python3
"""Read-only probe of the curated reverse-engineering stack.

Reads ``entrypoint/stack.json`` and reports, per tool, whether it is reachable on this
machine, which evidence tier it unlocks and which of the five named gaps it serves. It
installs nothing, starts nothing and changes nothing. The only network access is an
optional ``GET /health`` against the existing AgentDecompile listener (``--no-server`` to
skip; ``--server-url`` to override).

Examples::

    python3 entrypoint/setup/doctor.py
    python3 entrypoint/setup/doctor.py --json
    python3 entrypoint/setup/doctor.py --family addition --no-server
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

STACK = Path(__file__).resolve().parents[1] / "stack.json"
DEFAULT_URL = os.environ.get("AGENT_DECOMPILE_MCP_SERVER_URL") or os.environ.get(
    "AGENTDECOMPILE_MCP_SERVER_URL", "http://127.0.0.1:8080/mcp"
)


def health_url(mcp_url: str) -> str:
    base = mcp_url.rstrip("/")
    if base.endswith("/mcp"):
        base = base[: -len("/mcp")]
    return base + "/health"


def probe(tool: dict, *, server_url: str, check_server: bool) -> tuple[str, str]:
    """Return (state, detail). state is present, missing, skipped or unverified."""
    kind = tool["probe"]["kind"]
    value = tool["probe"]["value"]
    if kind == "none":
        return "skipped", "no probe defined"
    if kind == "bin":
        path = shutil.which(value)
        return ("present", path) if path else ("missing", f"{value} not on PATH")
    if kind == "python":
        try:
            found = importlib.util.find_spec(value) is not None
        except (ImportError, ValueError):
            found = False
        return ("present", f"import {value}") if found else ("missing", f"module {value} not importable")
    if kind == "env":
        raw = os.environ.get(value)
        if not raw:
            return "missing", f"${value} unset"
        return ("present", f"${value}={raw}") if Path(raw).exists() else ("missing", f"${value}={raw} does not exist")
    if kind == "http":
        if not check_server:
            return "skipped", "server probe disabled"
        url = health_url(server_url)
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 (local health endpoint)
                return "present", f"{url} -> {resp.status}"
        except urllib.error.URLError as exc:
            return "missing", f"{url} unreachable ({exc.reason}); diagnose ownership, do not start another server"
        except Exception as exc:  # pragma: no cover - defensive
            return "missing", f"{url} error ({exc})"
    return "skipped", f"unknown probe kind {kind}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stack", default=str(STACK), help="path to stack.json")
    parser.add_argument("--family", action="append", help="limit to a family (repeatable)")
    parser.add_argument("--server-url", default=DEFAULT_URL, help=f"existing MCP endpoint (default {DEFAULT_URL})")
    parser.add_argument("--no-server", action="store_true", help="skip the /health probe")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.stack).read_text(encoding="utf-8"))
    tools = data["tools"]
    if args.family:
        tools = [t for t in tools if t["family"] in set(args.family)]

    rows = []
    for tool in tools:
        state, detail = probe(tool, server_url=args.server_url, check_server=not args.no_server)
        if state == "missing" and not tool.get("verified_here", True):
            state = "unverified"
            detail += "; repository not confirmed, locate before installing"
        rows.append({
            "id": tool["id"],
            "name": tool["name"],
            "family": tool["family"],
            "status": tool["status"],
            "state": state,
            "detail": detail,
            "tier": tool.get("tier", []),
            "gap": tool.get("gap", []),
            "limits": tool.get("limits", ""),
        })

    present_tiers = sorted({t for r in rows if r["state"] == "present" for t in r["tier"]})
    gaps = data.get("gaps", {})
    gap_cover = {
        key: sorted(r["id"] for r in rows if r["state"] == "present" and key in r["gap"])
        for key in gaps
    }

    summary = {
        "server_url": args.server_url,
        "reachable_tiers": present_tiers,
        "gap_coverage": gap_cover,
        "counts": {s: sum(1 for r in rows if r["state"] == s) for s in ("present", "missing", "unverified", "skipped")},
        "tools": rows,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    width = max(len(r["name"]) for r in rows) if rows else 10
    print(f"AgentDecompile doctor (read-only)  server: {args.server_url}\n")
    for family in sorted({r["family"] for r in rows}, key=lambda f: (f != "core", f)):
        print(f"[{family}]")
        for r in rows:
            if r["family"] != family:
                continue
            mark = {"present": "ok ", "missing": "-- ", "unverified": "?? ", "skipped": "   "}[r["state"]]
            print(f"  {mark}{r['name']:<{width}}  {r['status']:<17} {r['detail']}")
        print()
    tiers = data.get("tiers", {})
    print("Reachable evidence tiers: " + (", ".join(f"{t} ({tiers.get(str(t), '')})" for t in present_tiers) or "none"))
    print("Gap coverage on this machine:")
    for key, label in gaps.items():
        print(f"  {label:<24} {', '.join(gap_cover[key]) or 'nothing present'}")
    c = summary["counts"]
    print(f"\n{c['present']} present, {c['missing']} missing, {c['unverified']} unverified, {c['skipped']} not probed.")
    print("Missing is information, not a blocker: lower the claim tier and say which checks could not run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
