#!/usr/bin/env python3
"""Compatibility entry point for in-process reload; no child supervisor.

Install the standalone inplace-hotreload wheel into the server's virtualenv first.
Existing --work-dir/--state-file arguments are accepted but no restart state is used.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--poll", type=float, default=None)
    parser.add_argument("--watch", type=Path, action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or Path(command[0]).name != "agentdecompile-server":
        parser.error("supply the virtualenv agentdecompile-server command after --")
    python = Path(command[0]).absolute().with_name("python")
    if not python.is_file():
        parser.error(f"server virtualenv Python not found: {python}")
    root = Path(__file__).resolve().parents[1]
    argv = [str(python), "-m", "inplace_hotreload"]
    for source in args.watch or [root / "src"]:
        argv.extend(["--root", str(source)])
    if args.poll is not None:
        if args.poll <= 0:
            parser.error("--poll must be positive")
        argv.extend(["--poll", str(args.poll)])
    argv.extend(["--call", "agentdecompile_cli.server:main", "--", *command[1:]])
    os.environ.pop("AGENT_DECOMPILE_RUNTIME_STATE_FILE", None)
    os.environ.pop("AGENT_DECOMPILE_RUNTIME_REVISION", None)
    os.environ.setdefault("AGENT_DECOMPILE_MATCH_CONCURRENCY", "2")
    os.chdir(root)
    os.execv(str(python), argv)


if __name__ == "__main__":
    main()
