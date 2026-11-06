#!/usr/bin/env bash
# Anonymization gate.
#
# Fails when a denylisted name token appears in the scanned part of the tree
# (contents and paths of git-tracked files; stage new files before running).
# The denylist itself lives OUTSIDE the repo:
#
#   AGENT_DECOMPILE_NAME_DENYLIST   path to the denylist file
#                                   (default: $XDG_CONFIG_HOME/agentdecompile/name-denylist.txt)
#   AGENT_DECOMPILE_NAME_BASELINE   path to the ratchet baseline
#                                   (default: scripts/anonymization-baseline.json)
#
# Denylist format: one token or phrase per line; blank lines and lines starting
# with '#' are ignored; matching is case-insensitive on word boundaries
# ('_' counts as a separator, so 'tok_x' hits and 'tokx' does not); whitespace
# inside a phrase also matches '_' or '-'.
#
# The baseline records hashed paths only: {"version": 1, "paths": {sha256(path)[:16]: hits}}.
# Output never contains a matched token or a plain path.
#
# Usage: scripts/check-anonymization.sh [--strict | --write-baseline]
#   (no flag)         ratchet: fail on any path whose hits are new or exceed the baseline
#   --strict          ignore the baseline; any hit fails
#   --write-baseline  regenerate the baseline from the current scan (the only way it changes)
#
# Exit codes: 0 pass, 1 hits over the allowed level, 2 the gate could not run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DENYLIST="${AGENT_DECOMPILE_NAME_DENYLIST:-${XDG_CONFIG_HOME:-$HOME/.config}/agentdecompile/name-denylist.txt}"
BASELINE="${AGENT_DECOMPILE_NAME_BASELINE:-scripts/anonymization-baseline.json}"

exec python3 - "$DENYLIST" "$BASELINE" "$@" <<'PY'
import hashlib
import json
import os
import re
import subprocess
import sys

SCAN_SET = ["src", "scripts", "tests", "docs", "pyproject.toml", "README.md", "AGENTS.md", "USAGE.md"]
EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", "target", "third_party"}
SELF_PATH = "scripts/check-anonymization.sh"
CHUNK = 400

denylist_path, baseline_path, *flags = sys.argv[1:]


def fail_config(message: str) -> None:
    print(f"Anonymization gate could not run: {message}")
    sys.exit(2)


mode = "ratchet"
for flag in flags:
    if flag == "--strict":
        mode = "strict"
    elif flag == "--write-baseline":
        mode = "write"
    elif flag in ("-h", "--help"):
        print("Usage: scripts/check-anonymization.sh [--strict | --write-baseline]")
        sys.exit(0)
    else:
        fail_config(f"unknown flag {flag!r}; use --strict or --write-baseline")
if "--strict" in flags and "--write-baseline" in flags:
    fail_config("--strict and --write-baseline cannot be combined")

# --- denylist -------------------------------------------------------------
if not os.path.isfile(denylist_path) or os.path.getsize(denylist_path) == 0:
    fail_config(
        f"the name denylist is missing or empty at {denylist_path!r}. "
        "Set AGENT_DECOMPILE_NAME_DENYLIST to a file outside the repo with one token or phrase per line; "
        "blank lines and lines starting with '#' are ignored; tokens are matched case-insensitively on "
        "word boundaries. The gate fails closed without it."
    )

tokens: list[str] = []
seen: set[str] = set()
with open(denylist_path, encoding="utf-8") as handle:
    for raw in handle:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key = " ".join(line.lower().split())
        if key in seen:
            continue
        seen.add(key)
        tokens.append(line)
if not tokens:
    fail_config(f"the name denylist at {denylist_path!r} has no tokens (only blank or comment lines)")


def rust_escape(token: str) -> str:
    parts = []
    for piece in re.split(r"\s+", token.strip()):
        parts.append(re.sub(r"[^A-Za-z0-9]", lambda m: "\\" + m.group(0), piece))
    return "[[:space:]_-]+".join(parts)


REGEX = "(^|[^A-Za-z0-9])(" + "|".join(rust_escape(t) for t in tokens) + ")([^A-Za-z0-9]|$)"
RG_BASE = ["rg", "--no-config", "--ignore-case", "-e", REGEX]

probe = subprocess.run(RG_BASE + ["--quiet", "--", os.devnull], capture_output=True, text=True)
if probe.returncode == 2:
    fail_config("the denylist produced a pattern rg rejects (the pattern is not shown); check the file for stray syntax")

# --- file set (tracked files only) ---------------------------------------------
present = [p for p in SCAN_SET if os.path.exists(p)]
if not present:
    fail_config("none of the scan paths exist here: " + " ".join(SCAN_SET))

ls = subprocess.run(["git", "ls-files", "-z", "--", *present], capture_output=True)
if ls.returncode != 0:
    fail_config("git ls-files failed; the gate needs to run inside a git work tree")


def excluded(path: str) -> bool:
    parts = path.split("/")
    for part in parts[:-1]:
        if part in EXCLUDED_DIRS or part.endswith(".egg-info"):
            return True
    base = parts[-1]
    return base.startswith("NOTICE") or base.startswith("LICENSE") or path == SELF_PATH


files = sorted(p for p in ls.stdout.decode("utf-8", "surrogateescape").split("\0") if p and not excluded(p) and os.path.isfile(p))

# --- content scan ---------------------------------------------------------------
hits: dict[str, int] = {}
rg_errors = 0
for start in range(0, len(files), CHUNK):
    chunk = files[start : start + CHUNK]
    run = subprocess.run(RG_BASE + ["--count", "--with-filename", "--", *chunk], capture_output=True, text=True, errors="surrogateescape")
    if run.returncode == 2 or run.stderr.strip():
        rg_errors += max(1, len(run.stderr.splitlines()))
    for line in run.stdout.splitlines():
        path, _, count = line.rpartition(":")
        if path and count.isdigit():
            hits[path] = hits.get(path, 0) + int(count)
if rg_errors:
    fail_config(f"rg reported {rg_errors} error line(s) while scanning (not shown); rerun rg by hand to see them")

# --- path scan (a denylisted token in a file name is a hit) --------------------------
run = subprocess.run(RG_BASE + ["--", "-"], input="\n".join(files) + "\n", capture_output=True, text=True, errors="surrogateescape")
if run.returncode == 2:
    fail_config("rg failed while scanning file names")
for path in run.stdout.splitlines():
    if path:
        hits[path] = hits.get(path, 0) + 1


def digest(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8", "surrogateescape")).hexdigest()[:16]


current: dict[str, int] = {}
for path, count in hits.items():
    current[digest(path)] = current.get(digest(path), 0) + count
total_hits = sum(current.values())

# --- baseline ----------------------------------------------------------------------
baseline: dict[str, int] = {}
baseline_note = "absent (every hit fails)"
if os.path.isfile(baseline_path):
    try:
        with open(baseline_path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != 1 or not isinstance(data.get("paths"), dict):
            raise ValueError("expected {'version': 1, 'paths': {...}}")
        baseline = {str(k): int(v) for k, v in data["paths"].items()}
    except (OSError, ValueError, TypeError) as exc:
        fail_config(f"the baseline at {baseline_path!r} is unreadable ({type(exc).__name__}); expected {{\"version\": 1, \"paths\": {{...}}}}")
    baseline_note = f"{len(baseline)} entries"

print(f"Anonymization gate: {len(files)} files scanned, {len(tokens)} tokens, baseline {baseline_note}, mode {mode}")

if mode == "write":
    added = sum(1 for h in current if h not in baseline)
    removed = sum(1 for h in baseline if h not in current)
    shrank = sum(1 for h in current if h in baseline and current[h] < baseline[h])
    grew = sum(1 for h in current if h in baseline and current[h] > baseline[h])
    with open(baseline_path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "paths": dict(sorted(current.items()))}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"Baseline written to {baseline_path}: {len(current)} entries, {total_hits} hits (added {added}, removed {removed}, shrank {shrank}, grew {grew})")
    sys.exit(0)

allowed = {} if mode == "strict" else baseline
new_paths = 0
grown_paths = 0
for h in sorted(current):
    count = current[h]
    if h not in allowed:
        status = "NEW"
        new_paths += 1
    elif count > allowed[h]:
        status = f"GREW (baseline {allowed[h]})"
        grown_paths += 1
    else:
        status = f"ok (baseline {allowed[h]})"
    print(f"  {h}  {count:4d}  {status}")

if mode == "strict":
    if current:
        print(f"Anonymization gate FAILED (strict): {total_hits} hits over {len(current)} paths")
        sys.exit(1)
    print("Anonymization gate OK (strict: 0 hits)")
    sys.exit(0)

if new_paths or grown_paths:
    print(
        f"Anonymization gate FAILED: {new_paths} new path(s), {grown_paths} grown path(s); "
        f"{total_hits} hits over {len(current)} paths. Remove the names, or if the increase is intended, "
        "run scripts/check-anonymization.sh --write-baseline and commit the baseline."
    )
    sys.exit(1)
print(f"Anonymization gate OK (baseline: {len(baseline)} paths, {total_hits} hits)")
PY
