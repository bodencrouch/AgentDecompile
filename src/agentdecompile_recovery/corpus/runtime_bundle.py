"""Launchable scenario bundles and combined behaviour/recording receipts (design rows F08, F15).

A06: a bundle becomes launchable only after its complete input closure, including indirect
staged libraries and fixtures named by other entries, is verified byte-for-byte on healthy
storage. Only then is ``launchable.json`` written, atomically. A missing or changed input
leaves the bundle unlaunchable; an unrelated complete bundle is unaffected.

A11: a passing behaviour oracle with a missing, truncated or uncorrelated recording keeps
its scoped behaviour receipt, but the combined "behaviour and video" claim is refused and
the same action must be rerun. Correlation means the same attempt and action, and a
recording interval covering the oracle's interval.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

LAUNCHABLE = "launchable.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def closure(manifest: dict) -> list[dict]:
    """Every entry the bundle needs, following ``requires`` to indirect libraries and fixtures."""
    entries = {e["path"]: e for e in manifest.get("entries", [])}
    seen: dict[str, dict] = {}
    stack = list(manifest.get("roots", entries))
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        entry = entries.get(path)
        if entry is None:
            seen[path] = {"path": path, "missing_declaration": True}
            continue
        seen[path] = entry
        stack.extend(entry.get("requires", ()))
    return [seen[p] for p in sorted(seen)]


def validate(bundle: Path | str, manifest: dict) -> dict:
    """Check the whole closure; write ``launchable.json`` only when every input verifies."""
    bundle = Path(bundle)
    marker = bundle / LAUNCHABLE
    problems = []
    for entry in closure(manifest):
        target = bundle / entry["path"]
        if entry.get("missing_declaration"):
            problems.append({"path": entry["path"], "reason": "required but not declared in the manifest"})
        elif not target.is_file():
            problems.append({"path": entry["path"], "reason": "missing"})
        elif _sha256(target) != entry.get("sha256"):
            problems.append({"path": entry["path"], "reason": "content differs from the manifest"})
    if problems:
        if marker.exists():
            marker.unlink()  # a bundle that stopped verifying is no longer launchable
        return {"launchable": False, "problems": problems}
    body = json.dumps({"manifestSha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                       "entries": len(closure(manifest))}, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir=bundle, prefix=".launchable.", suffix=".tmp")
    with os.fdopen(fd, "w") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, marker)
    return {"launchable": True, "problems": []}


def is_launchable(bundle: Path | str) -> bool:
    return (Path(bundle) / LAUNCHABLE).is_file()


def combine(oracle: dict, recording: dict | None) -> dict:
    """Combined behaviour-and-recording claim, or a refusal that keeps the behaviour receipt."""
    if not oracle.get("passed"):
        return {"combined": False, "behaviourReceipt": oracle, "reason": "behaviour oracle did not pass",
                "nextAction": "rerun_same_action"}
    problem = None
    if not recording:
        problem = "recording missing"
    elif recording.get("truncated"):
        problem = "recording truncated"
    elif (recording.get("attempt_id"), recording.get("action_id")) != (oracle.get("attempt_id"), oracle.get("action_id")):
        problem = "recording belongs to another attempt or action"
    elif not (recording.get("start", float("inf")) <= oracle.get("start", 0)
              and recording.get("end", float("-inf")) >= oracle.get("end", 0)):
        problem = "recording does not cover the oracle interval"
    if problem:
        return {"combined": False, "behaviourReceipt": oracle, "reason": problem, "nextAction": "rerun_same_action"}
    return {"combined": True, "behaviourReceipt": oracle, "recordingReceipt": recording}
