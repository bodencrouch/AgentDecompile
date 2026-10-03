"""G4 lifecycle-owner record and fail-closed ownership reconciliation.

One lifecycle owner holds a scenario's effective operation manifest (content,
not only its digest), the immutable staged-tree digest, the pinned fixture and
the process identities it launched.  ``reconcile`` decides whether a requester
may take or resume that ownership.  Unknown, competing, stale, drifted or
mismatched ownership becomes a *blocked* result with a bounded wake condition.
A blocked result deliberately names no location, alternate route or operator
step; a wake only asks for re-evaluation, never for admission.

Process identity is ``pid`` plus kernel start time (``/proc/PID/stat`` field
22) plus session ID (field 6).  A same-name process that no record attributes
is a reason to block, never a cleanup target.  This module performs no process
control, launches nothing and reads ``/proc`` only in ``observe_process``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

OWNER_FORMAT = "agentdecompile.runtime-lifecycle-owner/v1"
RESULT_FORMAT = "agentdecompile.runtime-lifecycle-reconciliation/v1"
OWNER_STATES = ("prepared", "running", "released", "quarantined")
PROCESS_ROLES = ("launcher", "game", "helper")

# Mirrors KotorPhasor scripts/harness/kpharness/scenario.py OperationPin so the
# digest here equals ``OperationPin.manifest_sha256()`` for the same pin.
_DIGEST_FIELDS = ("operation_contract_sha256", "target_sha256", "deployed_script_sha256",
                  "fixture_sha256", "runtime_sha256")
_STAGE_FIELDS = ("deployed_script", "fixture", "runtime_artifact")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_OPERATION_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_OWNER_KEYS = {"format", "generation", "state", "manifest", "manifest_sha256", "staged_bundle",
               "staged_tree_sha256", "fixture_sha256", "owner", "processes", "created_at"}


class LifecycleError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: object, where: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LifecycleError(f"{where}: must be 64 lowercase hexadecimal digits")
    return value


def _int(value: object, where: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise LifecycleError(f"{where}: must be an integer >= {minimum}")
    return value


def canonical_manifest(manifest: object) -> dict:
    """Validated copy of an effective operation manifest (the KotorPhasor pin)."""
    if not isinstance(manifest, dict) or set(manifest) != {"id", *_DIGEST_FIELDS, "staging"}:
        raise LifecycleError("manifest: requires exactly id, five digests and staging")
    if not isinstance(manifest["id"], str) or not _OPERATION_ID.fullmatch(manifest["id"]):
        raise LifecycleError("manifest.id: must be a lowercase stable operation ID")
    out: dict = {"id": manifest["id"]}
    for key in _DIGEST_FIELDS:
        out[key] = _sha(manifest[key], f"manifest.{key}")
    staging = manifest["staging"]
    if not isinstance(staging, dict) or set(staging) != set(_STAGE_FIELDS):
        raise LifecycleError("manifest.staging: requires exactly " + ", ".join(_STAGE_FIELDS))
    for key in _STAGE_FIELDS:
        value = staging[key]
        if (not isinstance(value, str) or not value or value.startswith("/")
                or any(c in value for c in ("\\", ":", "\0")) or ".." in value.split("/")):
            raise LifecycleError(f"manifest.staging.{key}: must be relative inside the staged tree")
    out["staging"] = {key: staging[key] for key in _STAGE_FIELDS}
    return out


def manifest_sha256(manifest: object) -> str:
    return hashlib.sha256(_canonical_bytes(canonical_manifest(manifest))).hexdigest()


def _identity(value: object, where: str) -> dict:
    if not isinstance(value, dict) or not {"pid", "start", "session"} <= set(value):
        raise LifecycleError(f"{where}: requires pid, start and session")
    start = value["start"]
    if not isinstance(start, str) or not start.isdigit():
        raise LifecycleError(f"{where}.start: must be kernel start ticks")
    return {"pid": _int(value["pid"], f"{where}.pid"), "start": start,
            "session": _int(value["session"], f"{where}.session")}


def _process(value: object, where: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"role", "pid", "start", "session"}:
        raise LifecycleError(f"{where}: requires exactly role, pid, start and session")
    if value["role"] not in PROCESS_ROLES:
        raise LifecycleError(f"{where}.role: unsupported")
    return {"role": value["role"], **_identity(value, where)}


def validate_owner_record(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) != _OWNER_KEYS or raw.get("format") != OWNER_FORMAT:
        raise LifecycleError("owner record: invalid format or fields")
    manifest = canonical_manifest(raw["manifest"])
    digest = _sha(raw["manifest_sha256"], "owner record.manifest_sha256")
    if hashlib.sha256(_canonical_bytes(manifest)).hexdigest() != digest:
        raise LifecycleError("owner record: manifest content does not match manifest_sha256")
    if raw["state"] not in OWNER_STATES:
        raise LifecycleError("owner record: invalid state")
    if not isinstance(raw["staged_bundle"], str) or not raw["staged_bundle"]:
        raise LifecycleError("owner record: staged_bundle must be a non-empty string")
    fixture = _sha(raw["fixture_sha256"], "owner record.fixture_sha256")
    if fixture != manifest["fixture_sha256"]:
        raise LifecycleError("owner record: fixture is not the manifest-pinned fixture")
    created = raw["created_at"]
    if isinstance(created, bool) or not isinstance(created, (int, float)) or not math.isfinite(created):
        raise LifecycleError("owner record: invalid created_at")
    if not isinstance(raw["processes"], list):
        raise LifecycleError("owner record: processes must be a list")
    processes = [_process(p, f"owner record.processes[{i}]") for i, p in enumerate(raw["processes"])]
    owner = _identity(raw["owner"], "owner record.owner")
    if set(raw["owner"]) != {"pid", "start", "session"}:
        raise LifecycleError("owner record.owner: requires exactly pid, start and session")
    return {"format": OWNER_FORMAT, "generation": _int(raw["generation"], "owner record.generation"),
            "state": raw["state"], "manifest": manifest, "manifest_sha256": digest,
            "staged_bundle": raw["staged_bundle"],
            "staged_tree_sha256": _sha(raw["staged_tree_sha256"], "owner record.staged_tree_sha256"),
            "fixture_sha256": fixture, "owner": owner, "processes": processes, "created_at": float(created)}


def build_owner_record(*, manifest: dict, staged_bundle: str, staged_tree_sha256: str, owner: dict,
                       fixture_sha256: str, generation: int, created_at: float,
                       processes: Optional[list] = None, state: str = "prepared") -> dict:
    canonical = canonical_manifest(manifest)
    return validate_owner_record({
        "format": OWNER_FORMAT, "generation": generation, "state": state, "manifest": canonical,
        "manifest_sha256": hashlib.sha256(_canonical_bytes(canonical)).hexdigest(),
        "staged_bundle": staged_bundle, "staged_tree_sha256": staged_tree_sha256,
        "fixture_sha256": fixture_sha256, "owner": owner, "processes": list(processes or []),
        "created_at": created_at})


def record_sha256(record: dict) -> str:
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _unique_object(pairs):
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise LifecycleError(f"owner record: duplicate field {key!r}")
        out[key] = value
    return out


def load_owner_record(path: Path | str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except LifecycleError:
        raise
    except (OSError, UnicodeError, ValueError, OverflowError) as e:
        raise LifecycleError(f"owner record: unreadable ({type(e).__name__})") from e
    return validate_owner_record(raw)


def observe_process(pid: int, *, proc_root: Path | str = "/proc") -> Optional[dict]:
    """Identity from ``stat`` only; ``None`` when absent, unreadable marker otherwise."""
    try:
        data = (Path(proc_root) / str(pid) / "stat").read_bytes().decode("latin-1")
    except FileNotFoundError:
        return None
    except OSError:
        return {"pid": pid, "readable": False}
    try:
        after = data[data.rindex(")") + 2:].split()
        return {"pid": pid, "start": after[19], "session": int(after[3])}
    except (ValueError, IndexError):
        return {"pid": pid, "readable": False}


def _observation(observation: object) -> tuple[dict, set, list, Optional[str]]:
    if not isinstance(observation, dict):
        raise LifecycleError("observation: must be an object")
    alive: dict = {}
    unreadable: set = set()
    for i, entry in enumerate(observation.get("processes", [])):
        if isinstance(entry, dict) and entry.get("readable") is False:
            unreadable.add(_int(entry.get("pid"), f"observation.processes[{i}].pid"))
        else:
            identity = _identity(entry, f"observation.processes[{i}]")
            alive[identity["pid"]] = identity
    candidates = [_identity(c, f"observation.candidates[{i}]")
                  for i, c in enumerate(observation.get("candidates", []))]
    tree = observation.get("staged_tree_sha256")
    return alive, unreadable, candidates, None if tree is None else _sha(tree, "observation.staged_tree_sha256")


def _key(identity: dict) -> dict:
    return {"pid": identity["pid"], "start": identity["start"]}


def reconcile(record: object, *, manifest: dict, requester: dict, observation: dict, now: float,
              attempt: int, wake_bound_seconds: float, max_attempts: int,
              record_digest: Optional[str] = None) -> dict:
    """Admit or block one lifecycle-ownership request; never proposes a workaround."""
    if (isinstance(wake_bound_seconds, bool) or not isinstance(wake_bound_seconds, (int, float))
            or not math.isfinite(wake_bound_seconds) or wake_bound_seconds <= 0):
        raise LifecycleError("wake_bound_seconds: must be finite and positive")
    _int(max_attempts, "max_attempts")
    _int(attempt, "attempt", minimum=0)
    wanted = manifest_sha256(manifest)
    requester = _identity(requester, "requester")
    alive, unreadable, candidates, tree = _observation(observation)

    def result(decision, reason, evidence, *, generation=None, exits=(), digest=record_digest):
        out = {"format": RESULT_FORMAT, "decision": decision, "reason": reason, "manifest_sha256": wanted,
               "requester": _key(requester), "generation": generation, "evidence": evidence,
               "observed_at": observation.get("observed_at"), "recorded_at": now,
               "terminal": False, "wake": None}
        if decision == "blocked":
            if attempt >= max_attempts:
                out["terminal"] = True
            else:
                any_of = [{"process_exit": _key(p)} for p in exits]
                any_of.append({"record_changes_from": digest})
                out["wake"] = {"reevaluate_when": {"any_of": any_of}, "not_after": now + wake_bound_seconds,
                               "attempt": attempt + 1, "max_attempts": max_attempts}
        return out

    if record is None:
        valid = None
    else:
        try:
            valid = validate_owner_record(record)
        except LifecycleError as e:
            return result("blocked", "unknown", [f"owner record invalid: {e}"])
        record_digest = record_digest or record_sha256(valid)

    recorded = [] if valid is None else [valid["owner"], *valid["processes"]]
    known = {(p["pid"], p["start"]) for p in recorded}
    hidden = sorted(p["pid"] for p in recorded if p["pid"] in unreadable)
    if hidden:
        return result("blocked", "unknown", [f"recorded identity unreadable for pid {pid}" for pid in hidden],
                      generation=valid["generation"], digest=record_digest)
    strays = [c for c in candidates if (c["pid"], c["start"]) not in known]
    if strays:
        return result("blocked", "unknown", [f"unattributed target-name process pid {c['pid']}" for c in strays],
                      generation=None if valid is None else valid["generation"], exits=strays,
                      digest=record_digest)
    if valid is None:
        return result("admit", None, ["no prior owner record"], generation=1)

    def live(identity):
        seen = alive.get(identity["pid"])
        return seen is not None and seen["start"] == identity["start"]

    survivors = [p for p in recorded if live(p)]
    generation = valid["generation"]
    if valid["state"] == "released":
        if survivors:
            return result("blocked", "stale", ["released record has live recorded identities"],
                          generation=generation, exits=survivors, digest=record_digest)
        return result("admit", None, ["predecessor released"], generation=generation + 1)
    if valid["state"] == "quarantined":
        return result("blocked", "stale", ["predecessor quarantined"], generation=generation,
                      exits=survivors, digest=record_digest)
    owner = valid["owner"]
    if not live(owner):
        return result("blocked", "stale", ["recorded owner identity is gone"], generation=generation,
                      exits=survivors, digest=record_digest)
    if _key(owner) != _key(requester):
        return result("blocked", "competing", ["recorded owner identity is live"], generation=generation,
                      exits=[owner], digest=record_digest)
    if valid["manifest_sha256"] != wanted:
        return result("blocked", "manifest_mismatch", ["owner holds a different effective manifest"],
                      generation=generation, digest=record_digest)
    if tree != valid["staged_tree_sha256"]:
        return result("blocked", "staging_drift", ["staged tree digest differs from the owner record"],
                      generation=generation, digest=record_digest)
    return result("admit", None, ["requester is the live recorded owner"], generation=generation)


def reconcile_file(path: Path | str, **kwargs) -> dict:
    """Reconcile against an on-disk record; unreadable records become ``unknown``."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return reconcile(None, **kwargs)
    except OSError as e:
        return reconcile({"unreadable": type(e).__name__}, **kwargs)
    digest = hashlib.sha256(data).hexdigest()
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (LifecycleError, UnicodeError, ValueError, OverflowError) as e:
        raw = {"unreadable": type(e).__name__}
    if not isinstance(raw, dict):
        raw = {"unreadable": "shape"}
    return reconcile(raw, **{**kwargs, "record_digest": digest})


def record_result(directory: Path | str, result: dict) -> Path:
    """Durably publish one result under its content digest; never overwrites."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = json.dumps(result, sort_keys=True, indent=2).encode() + b"\n"
    final = directory / (hashlib.sha256(data).hexdigest() + ".json")
    if final.exists():
        if final.read_bytes() != data:
            raise LifecycleError("result digest collision")
        return final
    fd, tmp = tempfile.mkstemp(prefix=".result.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, final)
        except FileExistsError:
            if final.read_bytes() != data:
                raise LifecycleError("result digest collision")
    finally:
        os.unlink(tmp)
    return final
