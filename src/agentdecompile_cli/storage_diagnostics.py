"""Read-only context for local storage exhaustion errors."""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path


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
