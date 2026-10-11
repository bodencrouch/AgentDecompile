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

_QUOTA_VALUE = re.compile(r"^(?P<amount>\d+(?:\.\d+)?)(?P<unit>[KMGTPE]?)(?P<exceeded>\*)?$", re.IGNORECASE)
_QUOTA_WARNING_HEADROOM = 0.10
_QUOTA_STOP_BYTES = 1024**3


@dataclass(frozen=True)
class _QuotaRow:
    mount: Path
    space_used: int
    space_quota: int | None
    space_limit: int | None
    inodes_used: int | None
    inodes_quota: int | None
    inodes_limit: int | None
    exceeded_marker: bool


def _quota_value(value: str) -> tuple[int | None, bool]:
    """Parse one `quota -s` number and retain its over-limit marker."""
    match = _QUOTA_VALUE.fullmatch(value.strip())
    if match is None:
        return None, False
    unit = match.group("unit").upper()
    power = "KMGTPE".find(unit) + 1 if unit else 0
    return int(float(match.group("amount")) * (1024**power)), bool(match.group("exceeded"))


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
        space_values = [_quota_value(cell) for cell in cells[2:5]]
        used, quota, limit = (value for value, _marked in space_values)
        if used is None:
            continue
        inode_values = [_quota_value(cell) for cell in cells[5:]]
        inode_values = [value for value in inode_values if value[0] is not None][:3]
        if len(inode_values) == 3:
            used_inodes, inode_quota, inode_limit = (value for value, _marked in inode_values)
        else:
            used_inodes = inode_quota = inode_limit = None
        exceeded_marker = any(marked for _value, marked in space_values + inode_values)
        rows.append(
            _QuotaRow(
                Path(cells[1]),
                used,
                quota,
                limit,
                used_inodes,
                inode_quota,
                inode_limit,
                exceeded_marker,
            )
        )
    return rows


def _mount_for_path(
    path: Path,
    rows: list[_QuotaRow],
) -> _QuotaRow | None:
    destination = path.expanduser().absolute()
    matches = [row for row in rows if destination == row.mount or row.mount in destination.parents]
    return max(matches, key=lambda row: len(row.mount.parts), default=None)


def _preflight_from_quota_output(
    paths: list[str | Path],
    output: str,
    quota_exit_code: int,
) -> list[str]:
    rows = _quota_rows(output)
    warnings: list[str] = []
    emitted: set[Path] = set()
    for path in paths:
        row = _mount_for_path(Path(path), rows)
        if row is None or row.mount in emitted:
            continue
        mount = row.mount
        space_quota = min((value for value in (row.space_quota, row.space_limit) if value and value > 0), default=0)
        inode_quota = min((value for value in (row.inodes_quota, row.inodes_limit) if value and value > 0), default=0)
        space_over_soft_quota = space_quota > 0 and row.space_used > space_quota
        inodes_over_soft_quota = inode_quota > 0 and row.inodes_used is not None and row.inodes_used > inode_quota
        space_exhausted = row.space_limit is not None and row.space_limit > 0 and row.space_used >= row.space_limit
        inodes_exhausted = (
            row.inodes_limit is not None
            and row.inodes_limit > 0
            and row.inodes_used is not None
            and row.inodes_used >= row.inodes_limit
        )
        if space_exhausted or inodes_exhausted or row.exceeded_marker or (
            quota_exit_code == 1 and (space_over_soft_quota or inodes_over_soft_quota)
        ):
            dimensions = []
            if space_exhausted or (quota_exit_code == 1 and space_over_soft_quota):
                dimensions.append("byte")
            if inodes_exhausted or (quota_exit_code == 1 and inodes_over_soft_quota):
                dimensions.append("inode")
            if not dimensions:
                dimensions.append("reported")
            raise RuntimeError(
                f"Local storage quota is exhausted at {mount} ({', '.join(dimensions)} quota). "
                "PyGhidra startup was stopped before opening the project because Ghidra may spend "
                "a long time attempting writes that cannot succeed. Select a destination with "
                "available user quota using --local-project-path, and configure JVM temp with "
                "JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/path if needed. No files were changed."
            )

        space_limit = min((limit for limit in (row.space_quota, row.space_limit) if limit and limit > 0), default=0)
        remaining = None
        space_headroom = None
        if space_limit > 0:
            remaining = max(0, space_limit - row.space_used)
            space_headroom = remaining / space_limit
            if (remaining <= _QUOTA_STOP_BYTES and space_headroom <= _QUOTA_WARNING_HEADROOM) or space_headroom <= 0.01:
                raise RuntimeError(
                    f"Local storage quota headroom is too low at {mount}: {remaining:,} bytes remain "
                    f"of {space_limit:,}. PyGhidra startup was stopped before a write could stall or "
                    "fail after a long wait. Select a project/temp destination with more user quota. "
                    "No files were changed."
                )
        if space_limit > 0 and space_headroom is not None and space_headroom <= _QUOTA_WARNING_HEADROOM:
            percent = max(0, round(100 * space_headroom))
            warnings.append(
                f"Near user quota at {mount}: {row.space_used:,} bytes used of {space_limit:,} bytes "
                f"({percent}% remaining). Large local Ghidra operations may fail when "
                "they write project or temporary data; execution will continue."
            )
            emitted.add(mount)
        if inode_quota > 0 and row.inodes_used is not None:
            remaining_inodes = max(0, inode_quota - row.inodes_used)
            inode_headroom = remaining_inodes / inode_quota
            if (remaining_inodes <= 10000 and inode_headroom <= _QUOTA_WARNING_HEADROOM) or inode_headroom <= 0.01:
                raise RuntimeError(
                    f"Local storage inode-quota headroom is too low at {mount}: {remaining_inodes:,} "
                    f"inodes remain of {inode_quota:,}. PyGhidra startup was stopped before a write "
                    "could stall or fail after a long wait. Select a project/temp destination with "
                    "more inode quota. No files were changed."
                )
            if inode_headroom <= _QUOTA_WARNING_HEADROOM:
                percent = max(0, round(100 * inode_headroom))
                warnings.append(
                    f"Near user inode quota at {mount}: {row.inodes_used:,} inodes used of "
                    f"{inode_quota:,} ({percent}% remaining). Local Ghidra operations may "
                    "fail when creating files; execution will continue."
                )
                emitted.add(mount)
    return warnings


def storage_preflight_warnings(paths: list[str | Path]) -> list[str]:
    """Return read-only warnings, stopping before Ghidra if a target is exhausted/low.

    This is deliberately advisory: workload size is unknown, quota reporting
    is platform-specific, and startup must never fail just because the optional
    system `quota` utility is missing or cannot query a mount. A confirmed
    exhausted quota or critically low headroom on a requested destination is
    different: Ghidra writes can stall before returning EDQUOT, so stop early.
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
    # quota(1) returns 1 when it reports a quota exceeded. Keep its stdout so
    # the exceeded marker can be matched to the actual project/temp mount.
    if result.returncode not in (0, 1):
        return []
    return _preflight_from_quota_output(paths, result.stdout, result.returncode)


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
