"""Live status of in-progress frontdoor recovery runs.

Reads directly from a run's `attempts.jsonl` ledger -- the append-only
compile/objdiff record the `agentdecompile-reconstruct` frontdoor pipeline
writes during its synthesize-source-tasks stage. This is a different run
concept from `preparation.list_runs` (interactive MCP-server workbench
sessions) or `recovery_status.corpus_status` (a `corpus.sqlite` import
snapshot) -- those can be minutes to days stale relative to a live
frontdoor invocation. Ledger status strings ("compile-failed", "mismatched",
"code-slice-matched") are surfaced verbatim, never summarized into a byte-
accuracy claim: a mismatched or code-slice-matched count is not full-image
byte identity.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

_SEARCH_ROOTS_ENV = "AGENTDECOMPILE_RECOVERY_SEARCH_ROOTS"
_DEFAULT_ROOTS = (
    "/home/brunner56/agentdecompile-nvme/agentdecompile_projects/corpus_work/recovery",
)
_TAIL_BYTES = 8 * 1024 * 1024
_TAIL_MAX_LINES = 4000
_MAX_WALK_DEPTH = 6
# Pruned before os.walk ever scandir's into them: each can hold tens of
# thousands of entries (one subdirectory per synthesis candidate/case, or one
# file per cached compile result), which made an unfiltered walk take 10+
# seconds per poll on this corpus -- long enough to stall the whole
# single-threaded ASGI request loop, hanging every other dashboard request.
_SKIP_DIR_NAMES = frozenset({
    "source-generation",
    "cases",
    "compile-cache",
    "acquisition",
    "wine-prefixes",
    "byte-authority",
    ".git",
})
_LEDGER_CACHE_TTL_SECONDS = 2.0
_ledger_cache: tuple[float, list[Path]] | None = None

# Observed-throughput samples, one per run directory, so the panel can report
# a real attempts/sec rate instead of guessing. Populated across successive
# polls of a long-lived dashboard server process; the first poll for a given
# run has no prior sample and reports no rate rather than a fabricated one.
_THROUGHPUT_SAMPLES: dict[str, tuple[float, int]] = {}
_CANDIDATE_TARGET_CACHE: dict[str, int] = {}


def _candidate_target(run_dir: Path) -> int | None:
    """Count of generated source candidates queued for this run's synthesize
    stage -- the denominator for "how far through the corpus", not a byte-
    accuracy count. Cached per run_dir: this directory's membership is set
    once by generate-source-candidates and doesn't change afterward."""
    key = str(run_dir)
    cached = _CANDIDATE_TARGET_CACHE.get(key)
    if cached is not None:
        return cached
    source_gen_dir = run_dir / "source-generation"
    if not source_gen_dir.is_dir():
        return None
    try:
        count = sum(1 for entry in os.scandir(source_gen_dir) if entry.is_dir())
    except OSError:
        return None
    _CANDIDATE_TARGET_CACHE[key] = count
    return count


def _search_roots() -> list[Path]:
    roots: list[Path] = []
    override = os.environ.get(_SEARCH_ROOTS_ENV)
    if override:
        roots.extend(Path(p).expanduser() for p in override.split(os.pathsep) if p.strip())
    for candidate in _DEFAULT_ROOTS:
        path = Path(candidate)
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def _find_ledgers(*, max_results: int = 200) -> list[Path]:
    global _ledger_cache
    now = time.time()
    if _ledger_cache is not None and now - _ledger_cache[0] < _LEDGER_CACHE_TTL_SECONDS:
        return _ledger_cache[1]

    found: list[Path] = []
    for root in _search_roots():
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune before os.walk scandir's into any of these.
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
            if "attempts.jsonl" in filenames:
                found.append(Path(dirpath) / "attempts.jsonl")
                # source-synthesis has no ledgers nested further beneath it.
                dirnames[:] = []
                continue
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= _MAX_WALK_DEPTH:
                dirnames[:] = []
            if len(found) >= max_results:
                _ledger_cache = (now, found)
                return found
    _ledger_cache = (now, found)
    return found


def _tail_status_counts(path: Path) -> dict[str, int]:
    """Status counts from the ledger tail -- a bounded read on multi-GB files."""
    counts: Counter[str] = Counter()
    try:
        size = path.stat().st_size
    except OSError:
        return {}
    try:
        with path.open("rb") as handle:
            if size > _TAIL_BYTES:
                handle.seek(size - _TAIL_BYTES)
                handle.readline()  # drop a partial leading line
            data = handle.read()
    except OSError:
        return {}
    for raw in data.splitlines()[-_TAIL_MAX_LINES:]:
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(row, dict):
            counts[str(row.get("status") or "unknown")] += 1
    return dict(counts)


_LINE_COUNT_CACHE: dict[str, tuple[int, int]] = {}  # ledger path -> (bytes counted so far, newline count)


def _total_line_count(path: Path) -> int | None:
    """Newline count, incremental across polls.

    A run-18-sized ledger grows continuously and a static (finished) run's
    ledger can be 90MB+; rescanning either one from byte 0 on every 3s poll
    was the dominant cost in a poll that used to take 2+ seconds. Append-only
    ledgers only ever grow, so counting just the bytes appended since the
    last poll and adding to the cached total is equivalent to a full rescan.
    """
    key = str(path)
    try:
        size = path.stat().st_size
    except OSError:
        return None
    counted_bytes, counted_lines = _LINE_COUNT_CACHE.get(key, (0, 0))
    if size < counted_bytes:
        # Ledger shrank/was replaced (new run reusing a stale path) -- rescan.
        counted_bytes, counted_lines = 0, 0
    try:
        with path.open("rb") as handle:
            handle.seek(counted_bytes)
            new_lines = sum(
                chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 20), b"")
            )
    except OSError:
        return None
    counted_lines += new_lines
    _LINE_COUNT_CACHE[key] = (size, counted_lines)
    return counted_lines


def live_recovery_runs(*, limit: int = 5) -> list[dict[str, Any]]:
    """Most-recently-written recovery-run ledgers, newest first."""
    ledgers = _find_ledgers()
    stats: list[tuple[Path, os.stat_result]] = []
    for ledger in ledgers:
        try:
            stats.append((ledger, ledger.stat()))
        except OSError:
            continue
    stats.sort(key=lambda item: item[1].st_mtime, reverse=True)

    now = time.time()
    out: list[dict[str, Any]] = []
    for ledger, stat in stats[:limit]:
        run_dir = ledger.parent.parent
        age_seconds = now - stat.st_mtime
        total = _total_line_count(ledger)

        rate_per_sec = None
        key = str(ledger)
        prior = _THROUGHPUT_SAMPLES.get(key)
        if prior is not None and total is not None:
            prior_time, prior_total = prior
            elapsed = now - prior_time
            if elapsed >= 1.0 and total >= prior_total:
                rate_per_sec = round((total - prior_total) / elapsed, 2)
        if total is not None:
            _THROUGHPUT_SAMPLES[key] = (now, total)

        out.append({
            "runDir": str(run_dir),
            "ledgerPath": str(ledger),
            "totalAttempts": total,
            "candidateTarget": _candidate_target(run_dir),
            "attemptsPerSecond": rate_per_sec,
            "recentStatusCounts": _tail_status_counts(ledger),
            "ledgerBytes": stat.st_size,
            "lastWriteAgeSeconds": round(age_seconds, 1),
            "active": age_seconds < 30,
            "claimBoundary": (
                "Ledger status counts are this run's compile/objdiff outcomes only, "
                "read from a bounded tail of the ledger for large files; they are "
                "not full-image byte-accuracy proof. candidateTarget counts queued "
                "source candidates, not distinct attempts (a candidate may be tried "
                "under multiple compiler profiles), so it is not a completion "
                "percentage. attemptsPerSecond is measured between polls of this "
                "server, not a projected estimate."
            ),
        })
    return out


def render_live_recovery_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live recovery status</title>
<link rel="stylesheet" href="/dashboard/static/workbench-tokens.css">
<style>
  /* Reuses this app's own design tokens (workbench-tokens.css + the palette
     workbench.css defines on :root) instead of a one-off color scheme, so
     this page reads as part of the dashboard rather than a bolted-on page. */
  :root {
    --bg: #1e1f22; --bg-sunken: #141517; --surface: #2b2d30; --surface-raised: #3c3f41;
    --border: #4b4d50; --border-strong: #6a6d70;
    --fg-max: #e6e6e6; --fg-body: #bbbbbb; --fg-head: #8c8c8c; --fg-dim: #6e6e6e;
    --accent: #4c78cc; --success: #5cba8a; --danger: #d36b5c;
    --font-ui: ui-sans-serif, "Segoe UI", Tahoma, system-ui, sans-serif;
    --font-mono: ui-monospace, "Cascadia Code", "Consolas", "SFMono-Regular", monospace;
  }
  body { font: 400 13px/1.5 var(--font-ui); margin: 0; padding: 24px; background: var(--bg-sunken); color: var(--fg-body); }
  h1 { font: 650 1.1rem/1.3 var(--font-ui); color: var(--fg-max); margin: 0 0 4px; }
  .sub { color: var(--fg-head); margin: 0 0 20px; font-size: var(--wb-type-body, 13px); }
  .run { border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; background: var(--surface); }
  .run.active { border-color: var(--success); }
  .run-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .run-path { font-family: var(--font-mono); font-size: 12px; color: var(--fg-head); word-break: break-all; }
  .badge { font-size: var(--wb-type-kicker, 11px); padding: 2px 8px; border-radius: 999px; background: var(--surface-raised); color: var(--fg-head); }
  .badge.active { background: color-mix(in srgb, var(--success) 25%, var(--surface-raised)); color: var(--success); }
  .counts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .count { padding: 6px 10px; border-radius: 6px; background: var(--bg-sunken); border: 1px solid var(--border); font-family: var(--font-mono); font-size: 12px; }
  .count b { color: var(--fg-max); }
  .claim { margin-top: 10px; font-size: 12px; color: var(--fg-dim); }
  .empty { color: var(--fg-head); }
  a { color: var(--accent); }
</style>
</head>
<body>
<h1>Live recovery status</h1>
<p class="sub">Reads each run's attempts.jsonl ledger directly. Updates every 3s. Not a byte-accuracy claim.</p>
<div id="runs"><p class="empty">Loading&hellip;</p></div>
<script>
async function refresh() {
  let data;
  try {
    const res = await fetch('/dashboard/api/live-recovery');
    data = await res.json();
  } catch (err) {
    return;
  }
  const root = document.getElementById('runs');
  const runs = data.runs || [];
  if (runs.length === 0) {
    root.innerHTML = '<p class="empty">No recovery-run ledgers found.</p>';
    return;
  }
  root.innerHTML = runs.map(run => {
    const counts = Object.entries(run.recentStatusCounts || {})
      .sort((a, b) => b[1] - a[1])
      .map(([status, n]) => `<div class="count">${status}: <b>${n}</b></div>`)
      .join('');
    return `<div class="run ${run.active ? 'active' : ''}">
      <div class="run-head">
        <span class="run-path">${run.runDir}</span>
        <span class="badge ${run.active ? 'active' : ''}">${run.active ? 'writing now' : 'idle ' + Math.round(run.lastWriteAgeSeconds) + 's'}</span>
      </div>
      <div>total attempts: <b>${run.totalAttempts ?? '?'}</b> of ${run.candidateTarget ?? '?'} queued candidates
        ${run.attemptsPerSecond ? ' &mdash; ' + run.attemptsPerSecond + ' attempts/sec' : ''}</div>
      <div class="counts">${counts}</div>
      <div class="claim">${run.claimBoundary}</div>
    </div>`;
  }).join('');
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""
