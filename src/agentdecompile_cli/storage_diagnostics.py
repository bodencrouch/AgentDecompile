"""Read-only context for local storage exhaustion errors."""
from __future__ import annotations

import errno
import os
import re
import shutil
import subprocess
import sys

from dataclasses import dataclass
from pathlib import Path

_QUOTA_SIZE = re.compile(r"^(?P<amount>\d+(?:\.\d+)?)(?P<unit>[KMGTPE]?)$", re.IGNORECASE)
_QUOTA_WARNING_HEADROOM = 0.10
_QUOTA_WARNING_BYTES = 1024**3


@dataclass(frozen=True)
class _QuotaRow:
    mount: Path
    space_used: int
    space_quota: int | None
    space_limit: int | None
    inodes_used: int | None
    inodes_quota: int | None
    inodes_limit: int | None


def _quota_size_bytes(value: str) -> int | None:
    """Parse one `quota -s` size cell, returning None for unlimited/unknown."""
    match = _QUOTA_SIZE.fullmatch(value.strip())
    if match is None:
        return None
    unit = match.group("unit").upper()
    power = "KMGTPE".find(unit) + 1 if unit else 0
    return int(float(match.group("amount")) * (1024**power))


def _quota_rows(output: str) -> list[_QuotaRow]:
    """Read quota(1) rows emitted with --show-mntpoint and -s.

    Rows contain device, mountpoint, used/quota/limit bytes, then the three
    corresponding inode columns.  Unknown or unlimited cells remain None.
    """
    rows: list[_QuotaRow] = []
    for line in output.splitlines():
        cells = line.split()
        if len(cells) < 8 or not cells[1].startswith("/"):
            continue
        used = _quota_size_bytes(cells[2])
        quota = _quota_size_bytes(cells[3])
        limit = _quota_size_bytes(cells[4])
        if used is None:
            continue
        try:
            used_inodes = int(cells[5])
            inode_quota = int(cells[6])
            inode_limit = int(cells[7])
        except ValueError:
            used_inodes = inode_quota = inode_limit = None
        rows.append(_QuotaRow(Path(cells[1]), used, quota, limit, used_inodes, inode_quota, inode_limit))
    return rows


def _mount_for_path(
    path: Path,
    rows: list[_QuotaRow],
) -> _QuotaRow | None:
    destination = path.expanduser().absolute()
    matches = [row for row in rows if destination == row.mount or row.mount in destination.parents]
    return max(matches, key=lambda row: len(row.mount.parts), default=None)


def storage_preflight_warnings(paths: list[str | Path]) -> list[str]:
    """Return read-only warnings for local destinations near a user quota.

    This is deliberately advisory: workload size is unknown, quota reporting
    is platform-specific, and starting a CLI must never fail just because the
    optional system `quota` utility is missing or cannot query a mount.  The
    bounded subprocess also avoids hanging startup on remote quota services.
    """
    if os.name != "posix":
        return []
    quota_command = shutil.which("quota")
    if quota_command is None:
        return []
    try:
        result = subprocess.run(
            [quota_command, "--no-wrap", "--human-readable", "--show-mntpoint"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    rows = _quota_rows(result.stdout)
    warnings: list[str] = []
    emitted: set[Path] = set()
    for path in paths:
        row = _mount_for_path(Path(path), rows)
        if row is None or row.mount in emitted:
            continue
        mount = row.mount
        space_limit = min((limit for limit in (row.space_quota, row.space_limit) if limit and limit > 0), default=0)
        if space_limit > 0:
            remaining = max(0, space_limit - row.space_used)
            if remaining <= _QUOTA_WARNING_BYTES or remaining / space_limit <= _QUOTA_WARNING_HEADROOM:
                percent = max(0, round(100 * remaining / space_limit))
                warnings.append(
                    f"Near user quota at {mount}: {row.space_used:,} bytes used of {space_limit:,} bytes "
                    f"({percent}% remaining). Large local Ghidra operations may fail when "
                    "they write project or temporary data; execution will continue."
                )
                emitted.add(mount)
        inode_limit = min((limit for limit in (row.inodes_quota, row.inodes_limit) if limit and limit > 0), default=0)
        if inode_limit > 0 and row.inodes_used is not None:
            remaining_inodes = max(0, inode_limit - row.inodes_used)
            if remaining_inodes <= 10000 or remaining_inodes / inode_limit <= _QUOTA_WARNING_HEADROOM:
                percent = max(0, round(100 * remaining_inodes / inode_limit))
                warnings.append(
                    f"Near user inode quota at {mount}: {row.inodes_used:,} inodes used of "
                    f"{inode_limit:,} ({percent}% remaining). Local Ghidra operations may "
                    "fail when creating files; execution will continue."
                )
                emitted.add(mount)
    return warnings


def storage_failure_message(error: BaseException | str, project_path: str | Path) -> str | None:
    original = str(error)
    current = error if isinstance(error, BaseException) else None
    seen: set[int] = set()
    kind = None
    messages = [original]
    while current is not None and id(current) not in seen and len(seen) < 16:
        seen.add(id(current))
        messages.append(str(current))
        if isinstance(current, OSError):
            if current.errno == errno.EDQUOT:
                kind = "quota"
            elif current.errno == errno.ENOSPC and kind is None:
                kind = "space"
        current = current.__cause__ or current.__context__
    combined = "\n".join(messages).lower()
    if "disk quota exceeded" in combined:
        kind = "quota"
    elif kind is None and "no space left on device" in combined:
        kind = "space"
    if kind is None:
        return None

    temporary = None
    jpype = sys.modules.get("jpype")
    if jpype is not None:
        try:
            if jpype.isJVMStarted():
                temporary = str(jpype.JClass("java.lang.System").getProperty("java.io.tmpdir"))
        except Exception:
            pass
    if temporary is None:
        configured = next((os.environ[name] for name in ("TMPDIR", "TEMP", "TMP") if os.environ.get(name)), None)
        temporary = f"not yet available; configured process temp: {configured}" if configured else "not yet available (JVM startup did not expose java.io.tmpdir)"
    reason = "Storage quota exceeded" if kind == "quota" else "Storage space or inode capacity exhausted"
    return (
        f"{original}\n{reason}. Project destination: {Path(project_path).absolute()}. "
        f"JVM temporary destination: {temporary}. "
        "Check user/project quotas, available bytes and inodes at these destinations; "
        "filesystem free space alone does not prove quota availability. "
        "Free only files you own or select a destination with available capacity. "
        "Use --local-project-path for a new project destination; JVM temp can be configured "
        "before startup using JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/path. "
        "The failing write location may differ from these destinations; no files were removed."
    )
