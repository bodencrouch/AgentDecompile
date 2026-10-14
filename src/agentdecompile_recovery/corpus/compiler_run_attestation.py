"""Bounded, redacted evidence for one AgentDecompile compiler invocation.

Records contain a redacted argv shape and a digest of the exact argv, plus
opaque deterministic hashes for paths. They do not serialize raw argv,
environment values, or filesystem paths. Hashes can still reveal equality and
permit guesses about low-entropy values. This is not a complete compiler/
toolchain identity: Wine services, loaded modules, host runtime libraries,
dynamic reads, and frozen snapshots remain outside its observation boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Mapping, Sequence


SCHEMA = "agentdecompile.compiler-run-attestation/v1"
SINK_ENV = "AGENT_DECOMPILE_COMPILER_ATTESTATION_DIR"
HASH_FILES_ENV = "AGENT_DECOMPILE_COMPILER_ATTESTATION_HASH_FILES"
MAX_OBSERVED_BYTES = 128 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024

GAPS = (
    "wine_server_state_and_loaded_modules_unobserved",
    "host_runtime_libraries_unobserved",
    "transitive_compiler_file_reads_unobserved",
    "source_and_toolchain_snapshots_not_frozen",
    "all_relevant_environment_and_external_state_not_proven",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _path_hash(path: Path) -> str:
    return hashlib.sha256(os.fsencode(str(path))).hexdigest()


def _argv_projection(argv: Sequence[str]) -> tuple[list[dict], str]:
    """Return non-value token classes and a digest of the exact ordered argv."""
    arguments = [str(argument) for argument in argv]
    projection = []
    for index, argument in enumerate(arguments):
        folded = argument.casefold()
        if folded in {"/nologo", "/c"}:
            kind = "compiler-switch"
        elif folded.startswith(("/tc", "/tp")):
            kind = "source-input-switch"
        elif folded.startswith("/fo"):
            kind = "output-path-switch"
        elif folded.startswith(("/i", "/fi")):
            kind = "include-or-forced-include-switch"
        elif argument.startswith("@"):
            kind = "response-file-reference"
        elif argument.startswith("/"):
            kind = "compiler-switch-or-value"
        else:
            kind = "path-or-argument"
        projection.append({"index": index, "kind": kind})
    return projection, hashlib.sha256(_canonical(arguments)).hexdigest()


def _file_snapshot(path: Path, budget: list[int], *, hash_file: bool) -> dict:
    """Observe one stable, non-symlink regular file within a shared byte budget."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("not-regular")
        digest = None
        if hash_file:
            if before.st_size > MAX_OBSERVED_BYTES - budget[0]:
                raise ValueError("observation-budget-exceeded")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, min(65536, MAX_OBSERVED_BYTES - budget[0] + 1))
                if not chunk:
                    break
                budget[0] += len(chunk)
                if budget[0] > MAX_OBSERVED_BYTES:
                    raise ValueError("observation-budget-exceeded")
                digest.update(chunk)
        after = os.fstat(descriptor)
        identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        stable = all(getattr(before, key) == getattr(after, key) for key in identity_fields)
        result = {"pathSha256": _path_hash(path), "size": after.st_size,
                  "stat": {key: getattr(after, key) for key in identity_fields},
                  "stableDuringObservation": stable,
                  "hashing": "enabled" if digest is not None else "disabled"}
        if digest is not None:
            result["sha256"] = digest.hexdigest()
        return result
    finally:
        os.close(descriptor)


def _observe_files(rows: Sequence[tuple[str, Path]], *, hash_files: bool) -> tuple[list[dict], list[str]]:
    budget = [0]
    observed, gaps = [], []
    for role, raw_path in rows:
        path = Path(raw_path)
        try:
            observed.append({"role": role, **_file_snapshot(path, budget, hash_file=hash_files)})
        except (OSError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            observed.append({"role": role, "pathSha256": _path_hash(path), "observed": False,
                             "reason": reason})
            gaps.append("file_input_unobserved:" + role)
        if budget[0] >= MAX_OBSERVED_BYTES:
            gaps.append("file_observation_budget_exhausted")
            break
    return observed, gaps


def observe_invocation_inputs(*, compiler: Path, wine: Path,
                              sources: Sequence[Path],
                              environment: Mapping[str, str]) -> tuple[list[dict], list[str]]:
    """Observe declared files before launch; this is not a frozen read-set."""
    rows = [("adapter", Path(__file__).with_name("compiler_msvc71.py")),
            ("attestationModule", Path(__file__)),
            ("pythonRuntime", Path(sys.executable)),
            ("compiler", compiler), ("wineLauncher", wine),
            *((f"source:{index:04d}", path) for index, path in enumerate(sources))]
    return _observe_files(rows, hash_files=environment.get(HASH_FILES_ENV) == "1")


def make_attestation(*, argv: Sequence[str], environment: Mapping[str, str],
                     compiler: Path, wine: Path, sources: Sequence[Path],
                     outputs: Sequence[Path], started_ns: int,
                     return_code: int | None, launch_error: str | None = None,
                     finished_ns: int | None = None,
                     files_before: tuple[list[dict], list[str]]) -> dict:
    """Capture one invocation without retaining environment values or source."""
    environment_bytes = _canonical({str(key): str(value)
                                    for key, value in sorted(environment.items())})
    hash_files = environment.get(HASH_FILES_ENV) == "1"
    inputs, input_gaps = files_before
    result_rows = [(f"sourceAfter:{index:04d}", path)
                   for index, path in enumerate(sources)]
    result_rows.extend((f"output:{index:04d}", path)
                       for index, path in enumerate(outputs))
    after, output_gaps = _observe_files(result_rows, hash_files=hash_files)
    before_sources = {row["role"].removeprefix("source:"): row
                      for row in inputs if row["role"].startswith("source:")}
    after_sources = {row["role"].removeprefix("sourceAfter:"): row
                     for row in after if row["role"].startswith("sourceAfter:")}
    changed_sources = []
    for source_id, before in before_sources.items():
        after_source = after_sources.get(source_id)
        if (after_source is None
                or before.get("sha256") != after_source.get("sha256")
                or before.get("stat") != after_source.get("stat")
                or before.get("stableDuringObservation") is not True
                or after_source.get("stableDuringObservation") is not True):
            changed_sources.append(source_id)
    changed_sources.sort()
    argv_projection, argv_sha256 = _argv_projection(argv)
    record = {
        "schema": SCHEMA,
        "complete": False,
        "claimBoundary": (
            "Per-adapter-invocation evidence only; not a complete toolchain basis, "
            "frozen input snapshot, object identity claim, or byte-equivalence proof."
        ),
        "argvSha256": argv_sha256,
        "argvCount": len(argv),
        "argvProjection": argv_projection,
        "argvValuesPersisted": False,
        "environment": {
            "sha256": hashlib.sha256(environment_bytes).hexdigest(),
            "keyNames": sorted(str(key) for key in environment),
            "valuesPersisted": False,
        },
        "process": {
            "adapterObservedReturnCode": return_code,
            "launchError": launch_error,
            "durationNs": max(0, (finished_ns or time.monotonic_ns()) - started_ns),
            "pid": None,
            "pidUnavailableReason": "subprocess.run does not expose the child PID",
        },
        "filesBefore": inputs,
        "filesAfter": after,
        "fileHashesEnabled": hash_files,
        "sourcesChangedOrUnstableDuringInvocation": changed_sources,
        "unknowns": sorted(set((*GAPS, *input_gaps, *output_gaps,
                                 *(("source_changed_or_unstable_during_invocation",)
                                   if changed_sources else ())))),
    }
    if len(_canonical(record)) > MAX_RECORD_BYTES:
        # Keep logs bounded. The exact argv digest remains available, while
        # token-by-token shape is omitted for this exceptional oversized record.
        record["argvProjection"] = [{"omitted": True, "reason": "record-size-limit"}]
        record["filesBefore"] = [{key: value for key, value in row.items()
                                  if key in {"role", "observed", "reason"}}
                                 for row in inputs]
        record["filesAfter"] = [{key: value for key, value in row.items()
                                 if key in {"role", "observed", "reason"}}
                                for row in after]
        record["unknowns"] = sorted(set((*record["unknowns"], "record_size_limit_exceeded",
                                         "argv_projection_omitted_record_size_limit")))
    record["attestationSha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    return record


def emit_attestation(record: dict, *, sink_directory: str | None = None) -> str | None:
    """Write canonical JSON to stderr and optionally to a verified private sink."""
    import sys

    payload = _canonical(record) + b"\n"
    print("AGENT_DECOMPILE_COMPILER_RUN_ATTESTATION=" + payload.decode("ascii").rstrip(),
          file=sys.stderr)
    sink_path = None
    if sink_directory:
        directory = Path(sink_directory).expanduser()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY |
                               getattr(os, "O_NOFOLLOW", 0))
        try:
            metadata = os.fstat(directory_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("attestation sink must be a directory")
            if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise ValueError("attestation sink must be owned by this user with private permissions")
            name = f"compiler-run-{time.time_ns()}-{os.getpid()}.json"
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 getattr(os, "O_NOFOLLOW", 0), 0o600,
                                 dir_fd=directory_fd)
            try:
                opened = os.fstat(descriptor)
                if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                        or opened.st_mode & 0o077):
                    raise ValueError("attestation sidecar file is not private")
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(descriptor)
                os.fsync(directory_fd)
            finally:
                os.close(descriptor)
            sink_path = _path_hash(directory / name)
        finally:
            os.close(directory_fd)
    return sink_path
