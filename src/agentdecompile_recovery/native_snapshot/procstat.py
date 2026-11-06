"""Process-tree metrics from ``/proc`` (Linux): CPU seconds, PSS high-water, child counts.

Used by the bench harness to measure a JVM lane together with the native
``decompile`` processes it spawns, and by the integration test to prove that
the batch API leaks no ``decompile`` child.  No JVM, no third-party modules.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

_PROC = Path("/proc")
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


@dataclass(slots=True)
class ProcStat:
    pid: int
    comm: str
    state: str
    ppid: int
    utime: int
    stime: int
    cutime: int
    cstime: int

    @property
    def cpu_s(self) -> float:
        """CPU seconds of this process alone (not reaped children)."""
        return (self.utime + self.stime) / _CLK_TCK

    @property
    def reaped_children_cpu_s(self) -> float:
        return (self.cutime + self.cstime) / _CLK_TCK


def parse_stat_line(line: str) -> ProcStat | None:
    """Parse one ``/proc/<pid>/stat`` line; ``comm`` may contain spaces and parentheses."""
    start = line.find("(")
    end = line.rfind(")")
    if start < 0 or end < 0 or end < start:
        return None
    try:
        pid = int(line[:start].strip())
    except ValueError:
        return None
    comm = line[start + 1 : end]
    rest = line[end + 2 :].split()
    if len(rest) < 15:
        return None
    try:
        return ProcStat(pid=pid, comm=comm, state=rest[0], ppid=int(rest[1]), utime=int(rest[11]), stime=int(rest[12]), cutime=int(rest[13]), cstime=int(rest[14]))
    except ValueError:
        return None


def read_stat(pid: int) -> ProcStat | None:
    try:
        return parse_stat_line((_PROC / str(pid) / "stat").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def snapshot_all() -> dict[int, ProcStat]:
    """All live processes keyed by pid (one ``/proc`` scan)."""
    out: dict[int, ProcStat] = {}
    try:
        entries = os.listdir(_PROC)
    except OSError:
        return out
    for name in entries:
        if not name.isdigit():
            continue
        stat = read_stat(int(name))
        if stat is not None:
            out[stat.pid] = stat
    return out


def descendants(pid: int, table: dict[int, ProcStat] | None = None) -> list[ProcStat]:
    """Every live descendant of ``pid`` (children, grandchildren, ...), excluding ``pid`` itself."""
    table = table if table is not None else snapshot_all()
    by_parent: dict[int, list[ProcStat]] = {}
    for stat in table.values():
        by_parent.setdefault(stat.ppid, []).append(stat)
    out: list[ProcStat] = []
    stack = [pid]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        for child in by_parent.get(current, ()):
            if child.pid in seen:
                continue
            seen.add(child.pid)
            out.append(child)
            stack.append(child.pid)
    return out


def count_named(pid: int, comm: str, table: dict[int, ProcStat] | None = None) -> int:
    """How many live descendants of ``pid`` have ``comm`` (e.g. ``"decompile"``), zombies excluded."""
    return sum(1 for stat in descendants(pid, table) if stat.comm == comm and stat.state != "Z")


def pss_kb(pid: int) -> int:
    """Proportional set size in KiB from ``smaps_rollup``; falls back to ``VmRSS`` from ``status``."""
    try:
        for line in (_PROC / str(pid) / "smaps_rollup").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Pss:"):
                return int(line.split()[1])
    except OSError:
        pass
    try:
        for line in (_PROC / str(pid) / "status").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


def tree_pss_mb(pid: int, table: dict[int, ProcStat] | None = None) -> float:
    """PSS of ``pid`` plus every live descendant, in MiB."""
    total_kb = pss_kb(pid)
    for stat in descendants(pid, table):
        if stat.state != "Z":
            total_kb += pss_kb(stat.pid)
    return total_kb / 1024.0


def tree_cpu_s(pid: int, table: dict[int, ProcStat] | None = None) -> float:
    """CPU seconds of ``pid`` and its live descendants plus what ``pid`` already reaped."""
    table = table if table is not None else snapshot_all()
    root = table.get(pid) or read_stat(pid)
    total = 0.0
    if root is not None:
        total += root.cpu_s + root.reaped_children_cpu_s
    for stat in descendants(pid, table):
        total += stat.cpu_s
    return total


@dataclass(slots=True)
class TreeStats:
    pss_hwm_mb: float = 0.0
    child_hwm: int = 0
    named_child_hwm: int = 0
    cpu_s_last_seen: float = 0.0
    samples: int = 0
    interval_s: float = 0.2
    pss_series_mb: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "pss_hwm_mb": round(self.pss_hwm_mb, 1),
            "child_hwm": self.child_hwm,
            "named_child_hwm": self.named_child_hwm,
            "cpu_s_last_seen": round(self.cpu_s_last_seen, 2),
            "samples": self.samples,
            "interval_s": self.interval_s,
        }


class TreeSampler:
    """Background sampler over a process tree: PSS high-water, child high-water, last-seen CPU."""

    def __init__(self, pid: int, *, interval_s: float = 0.2, named: str = "decompile", keep_series: bool = False) -> None:
        self.pid = pid
        self.named = named
        self.stats = TreeStats(interval_s=interval_s)
        self._keep_series = keep_series
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"procstat-{pid}", daemon=True)

    def sample_once(self) -> None:
        table = snapshot_all()
        if self.pid not in table:
            return
        kids = descendants(self.pid, table)
        live = [k for k in kids if k.state != "Z"]
        pss = tree_pss_mb(self.pid, table)
        self.stats.samples += 1
        self.stats.pss_hwm_mb = max(self.stats.pss_hwm_mb, pss)
        self.stats.child_hwm = max(self.stats.child_hwm, len(live))
        self.stats.named_child_hwm = max(self.stats.named_child_hwm, sum(1 for k in live if k.comm == self.named))
        self.stats.cpu_s_last_seen = max(self.stats.cpu_s_last_seen, tree_cpu_s(self.pid, table))
        if self._keep_series:
            self.stats.pss_series_mb.append(round(pss, 1))

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample_once()
            self._stop.wait(self.stats.interval_s)

    def start(self) -> TreeSampler:
        self._thread.start()
        return self

    def stop(self) -> TreeStats:
        self._stop.set()
        self._thread.join(timeout=5.0)
        self.sample_once()
        return self.stats

    def __enter__(self) -> TreeSampler:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def wait_until_named_count(pid: int, comm: str, target: int, *, timeout_s: float = 5.0, poll_s: float = 0.1) -> int:
    """Poll until ``count_named(pid, comm) <= target`` or ``timeout_s`` passes; returns the last count."""
    deadline = time.monotonic() + timeout_s
    count = count_named(pid, comm)
    while count > target and time.monotonic() < deadline:
        time.sleep(poll_s)
        count = count_named(pid, comm)
    return count
