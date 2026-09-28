#!/usr/bin/env python3
"""Check routine static action ownership without a server, JVM, build or test suite.

Run from any directory. An optional static directory supports checking a staged
checkout. This is a source-policy check, not browser/runtime acceptance.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentdecompile_cli.mcp_server.program_metadata import static_surface_action_violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("static_dir", nargs="?", type=Path,
                        default=ROOT / "src/agentdecompile_recovery/corpus/dashboard/static")
    args = parser.parse_args()
    count = 0
    for name in ("actions.js", "workbench-app.js", "explorer-page.js"):
        path = args.static_dir / name
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            count += 1
            continue
        for violation in static_surface_action_violations(source):
            print(f"{path}:{violation['line']}: {violation['action']} "
                  f"({violation['classification']}): {violation['message']}")
            count += 1
    print(f"Static action ownership: {count} violation(s) across 3 required surfaces.")
    return 1 if count else 0


if __name__ == "__main__":
    raise SystemExit(main())
