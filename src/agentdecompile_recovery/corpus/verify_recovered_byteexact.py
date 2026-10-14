"""Compile recovered C and record raw and relocation-masked local comparisons.

Relocation masking is a scheduling diagnostic. It does not verify relocation
semantics, linking, or whole-image acceptance. `rawEqual` separately records an
exact-length raw comparison against the captured mapped target region. Copying
original operands into emitted substitutions is not evidence of recovered code.
Failed inputs and emitted mismatch objects are retained in the source pool's
bounded `.compiler-diagnostics` store, separate from exact and max-C artifacts.
Retention does not grant verification or authorize cached-success reuse.

Not a test file: this is a verification pass that writes receipts. Run:

    python3 -m agentdecompile_recovery.corpus.verify_recovered_byteexact \\
        --verified-dir <.../source/verified_c> --raw <raw_image> \\
        --compiler <compiler_msvc71.py> --out <receipts.json> [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import os
import signal
import re
import struct
import subprocess
import tempfile
import time
import shutil
import shlex
import sqlite3
import sys
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from .compiler_msvc71 import MAX_BATCH_TRANSLATION_UNITS, MIN_BATCH_TRANSLATION_UNITS, SOURCE_LANGUAGES, source_language
from .recovered_c_preamble import PREAMBLE as _PREAMBLE, preamble_for_source
from . import coff_object, source_claims
from .coff_object import parse_object_inventory

_BATCH_POLICY = {
    "compilerAdapter": "compiler_msvc71.py",
    "sourceLanguages": SOURCE_LANGUAGES,
    "minTranslationUnits": MIN_BATCH_TRANSLATION_UNITS,
    "maxTranslationUnits": MAX_BATCH_TRANSLATION_UNITS,
    "maxInFlightGroups": 1,
    "nonBatchGroupSize": 1,
}


def _normalized_source(path: Path, source: str) -> bytes:
    # Native C++ is a supplied translation unit. C compatibility aliases (bool,
    # NULL casts, etc.) are not native C++ declarations and must not be injected.
    preamble = preamble_for_source(source) if source_language(path) == 'c' else ''
    return (preamble + source).encode('utf-8')


def _compiler_batch_capable(compiler: str) -> bool:
    return Path(compiler).name == _BATCH_POLICY["compilerAdapter"]


def _compiler_environment(compiler: str, options: str | None) -> dict[str, str]:
    """Capture child inputs without mutating shared process environment."""
    environment = dict(os.environ)
    if options is not None:
        if Path(compiler).resolve() != Path(__file__).with_name('compiler_msvc71.py').resolve():
            raise ValueError('compiler-options requires the owned MSVC adapter')
        if len(options) > 4096 or any(character in options for character in '\0\r\n'):
            raise ValueError('compiler-options must be a bounded single-line option string')
        environment['CL_OPT'] = shlex.join(shlex.split(options))
    return environment


def _verification_group_size(batch_capable: bool) -> int:
    return (_BATCH_POLICY["maxTranslationUnits"] if batch_capable
            else _BATCH_POLICY["nonBatchGroupSize"])


def _verification_group_limit(batch_capable: bool, workers: int) -> int:
    return (_BATCH_POLICY["maxInFlightGroups"] if batch_capable
            else max(1, workers))


def _write_json_atomic(path: Path, value: object) -> None:
    """Replace a checkpoint only after its complete JSON is written beside it."""
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


_OWNER_SCHEMA = "agentdecompile.artifact-owners/v1"
_OWNER_MANIFEST = ".agentdecompile-artifact-owners.json"


class ArtifactPublicationError(RuntimeError):
    def __init__(self, diagnostics: list[dict]):
        super().__init__("artifact publication blocked")
        self.diagnostics = diagnostics


def _load_artifact_owners(root: Path) -> dict[str, dict]:
    try:
        document = json.loads((root / _OWNER_MANIFEST).read_text())
        owners = document.get("owners") if document.get("schema") == _OWNER_SCHEMA else None
        return {name: owner for name, owner in owners.items()
                if isinstance(name, str) and isinstance(owner, dict)} if isinstance(owners, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _write_artifact_owners(root: Path, owners: dict[str, dict]) -> None:
    _write_json_atomic(root / _OWNER_MANIFEST, {"schema": _OWNER_SCHEMA, "owners": owners})


def _result_address(result: dict) -> int | None:
    try:
        value = result.get("addr")
        address = value if type(value) is int else int(value, 16) if isinstance(value, str) else None
        return address if address is not None and address >= 0 else None
    except ValueError:
        return None


def _withdraw_manifest_sources(artifact_roots: dict[str, Path],
                               artifact_owners: dict[str, dict[str, dict]],
                               source_paths: set[str]) -> list[str]:
    """Withdraw durable source-owned artifacts without relying on cache state."""
    withdrawn = []
    blocked = []
    for root_key, root in artifact_roots.items():
        changed = False
        owners = artifact_owners[root_key]
        for name, owner in list(owners.items()):
            if not isinstance(owner, dict) or owner.get("sourcePath") not in source_paths:
                continue
            address = owner.get("address")
            path = root / name
            if (type(address) is not int or address < 0 or name != f"{address:08x}.bin"
                    or not isinstance(owner.get("sourceSha256"), str)
                    or not isinstance(owner.get("basis"), str)
                    or not isinstance(owner.get("sha256"), str)
                    or not isinstance(owner.get("channel"), str)):
                blocked.append({"path": str(path.resolve()), "sourcePath": owner.get("sourcePath"),
                                "reason": "durable_artifact_owner_invalid"})
                continue
            try:
                if path.is_file():
                    if _digest(path.read_bytes()) != owner["sha256"]:
                        blocked.append({"path": str(path.resolve()),
                                        "sourcePath": owner["sourcePath"], "address": address,
                                        "reason": "artifact_digest_mismatch"})
                        continue
                    quarantine = root / ".withdrawn"
                    quarantine.mkdir(exist_ok=True)
                    destination = quarantine / (
                        f"{path.name}.{owner['basis'][:12]}.{owner['sha256'][:12]}.{time.time_ns()}"
                    )
                    os.replace(path, destination)
                    withdrawn.append(str(destination.resolve()))
                owners.pop(name, None)
                changed = True
            except OSError as exc:
                blocked.append({"path": str(path.resolve()), "sourcePath": owner["sourcePath"],
                                "address": address, "reason": "artifact_quarantine_failed",
                                "error": exc.__class__.__name__})
        if changed:
            _write_artifact_owners(root, owners)
    if blocked:
        raise ArtifactPublicationError(blocked)
    return withdrawn

_ADDR_RE = re.compile(r"address:\s*(0x[0-9a-fA-F]+)")
_SIZE_RE = re.compile(r"size:\s*(\d+)\s*bytes")
_FUNC_RE = re.compile(r"\b(F_[0-9a-fA-F]+)\s*\(")
# Some recovered-C pools (MizuchiRE/recovered-source, recovered_candidates)
# embed the shipped bytes and encode the address in the function name
# (e.g. `Unwind_00717140`) instead of an `address:` header + `F_<addr>` name.
_MC_RE = re.compile(r"original machine code:[ \t]*([^\s*]+)")
_NAMEADDR_RE = re.compile(r"\b[A-Za-z_]\w*_([0-9a-fA-F]{6,8})\s*\(")
_ADDRESS_SELECTOR_RE = re.compile(r"(?:0[xX])?([0-9a-fA-F]{6,16})\Z")
_COMPILER_ATTESTATION_MARKER = "AGENT_DECOMPILE_COMPILER_RUN_ATTESTATION="
_COMPILER_ATTESTATION_SCHEMA = "agentdecompile.compiler-run-attestation/v1"
_COMPILER_ATTESTATION_MAX_BYTES = 1024 * 1024


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def _path_hash_for_binding(path: Path) -> str:
    return hashlib.sha256(os.fsencode(str(Path(path).resolve()))).hexdigest()


def _assembly_floor_reason(source: bytes) -> str | None:
    """Use the verification policy itself when ranking assembly-floor inputs.

    The short marker catches generated byte stubs cheaply. Naked/inline-asm
    shims are also assembly floor even when they lack that marker; sharing the
    source-claim predicate prevents them from consuming early C-verification
    slots before `_prepare_verification` rejects them.
    """
    if b"compile-only-asm" in source[:2000]:
        return "compile-only-asm"
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeError:
        return None
    # Most files have no shim token at all. Use the already-authoritative
    # pattern as a cheap prefilter, then run its comment/string-aware check
    # only on candidates that might contain one.
    if source_claims.SHIM_RE.search(text) is None:
        return None
    return source_claims._c_shim_match(text)


def _candidate_is_assembly_floor(path: Path) -> bool:
    """Rank likely shim sources without reading/parsing every whole file.

    Generated byte stubs identify themselves in the opening banner. For
    unmarked inputs, inspect the head and tail for a possible shim token; only
    those few candidates need the authoritative full-source classifier.
    Verification still applies that full classifier before compilation.
    """
    with path.open("rb") as source:
        prefix = source.read(2000)
        if b"compile-only-asm" in prefix:
            return True
        hinted = source_claims.SHIM_RE.search(prefix.decode("utf-8", errors="replace")) is not None
        if not hinted:
            size = path.stat().st_size
            if size > len(prefix):
                source.seek(max(0, size - 2000))
                suffix = source.read()
                hinted = source_claims.SHIM_RE.search(suffix.decode("utf-8", errors="replace")) is not None
    if not hinted:
        return False
    return _assembly_floor_reason(path.read_bytes()) is not None


def _compiler_run_attestation(stderr: str | bytes | None, *,
                              sources: list[Path] | None = None,
                              outputs: list[Path] | None = None,
                              process_returncode: int | None = None) -> dict:
    """Keep a bounded, sanitized adapter report; never call it authenticated.

    Path-role checks bind a report to this wrapper's declared inputs/outputs,
    but the compiler process controls stderr and can forge the marker. The
    digest proves payload consistency only, not origin or compiler identity.
    """
    unavailable = {"status": "marker-not-found", "diagnosticOnly": True,
                   "complete": False}
    if stderr is None:
        return unavailable
    if isinstance(stderr, bytes):
        try:
            text = stderr.decode("utf-8", errors="strict")
        except UnicodeError:
            return {"status": "marker-malformed", "reason": "stderr-not-utf8",
                    "diagnosticOnly": True, "complete": False}
    else:
        text = stderr
    markers = [line[len(_COMPILER_ATTESTATION_MARKER):]
               for line in text.splitlines()
               if line.startswith(_COMPILER_ATTESTATION_MARKER)]
    if not markers:
        return unavailable
    if len(markers) != 1:
        return {"status": "marker-malformed", "reason": "multiple-markers",
                "diagnosticOnly": True, "complete": False}
    payload = markers[0]
    try:
        encoded = payload.encode("ascii", errors="strict")
        if len(encoded) > _COMPILER_ATTESTATION_MAX_BYTES:
            raise ValueError("record-size-limit")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate-json-key")
                result[key] = value
            return result

        record = json.loads(encoded, object_pairs_hook=unique_object)
        if not isinstance(record, dict) or record.get("schema") != _COMPILER_ATTESTATION_SCHEMA:
            raise ValueError("unsupported-schema")
        if record.get("complete") is not False:
            raise ValueError("unexpected-completeness-claim")
        claimed_digest = record.get("attestationSha256")
        if not isinstance(claimed_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", claimed_digest):
            raise ValueError("invalid-attestation-digest")
        unsigned = dict(record)
        del unsigned["attestationSha256"]
        actual_digest = _digest(_canonical_json_bytes(unsigned))
        if actual_digest != claimed_digest or _canonical_json_bytes(record) != encoded:
            raise ValueError("attestation-canonical-digest-mismatch")
        # Persist only a strict, bounded projection. A self-consistent marker
        # may still be forged by any compiler/wrapper that controls stderr.
        expected_top = {"schema", "complete", "claimBoundary", "argvSha256", "argvCount",
                        "argvProjection", "argvValuesPersisted", "environment", "process",
                        "filesBefore", "filesAfter", "fileHashesEnabled",
                        "sourcesChangedOrUnstableDuringInvocation", "unknowns",
                        "attestationSha256"}
        if set(record) != expected_top:
            raise ValueError("unexpected-attestation-fields")
        if (type(record.get("argvCount")) is not int or record["argvCount"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("argvSha256", "")))
                or record.get("argvValuesPersisted") is not False
                or type(record.get("fileHashesEnabled")) is not bool):
            raise ValueError("invalid-attestation-summary")
        environment_record = record.get("environment")
        process_record = record.get("process")
        if (not isinstance(environment_record, dict)
                or set(environment_record) != {"sha256", "keyNames", "valuesPersisted"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(environment_record.get("sha256", "")))
                or environment_record.get("valuesPersisted") is not False
                or not isinstance(environment_record.get("keyNames"), list)
                or not isinstance(process_record, dict)
                or set(process_record) != {"adapterObservedReturnCode", "launchError", "durationNs",
                                            "pid", "pidUnavailableReason"}
                or type(process_record.get("durationNs")) is not int
                or process_record["durationNs"] < 0
                or (process_record.get("adapterObservedReturnCode") is not None
                    and type(process_record.get("adapterObservedReturnCode")) is not int)):
            raise ValueError("invalid-attestation-process-or-environment")
        if (process_returncode is not None
                and process_record.get("adapterObservedReturnCode") != process_returncode):
            raise ValueError("adapter-return-code-mismatch")

        expected_sources = sources or []
        expected_outputs = outputs or []
        expected_source_hashes = {
            f"source:{index:04d}": _path_hash_for_binding(path)
            for index, path in enumerate(expected_sources)
        }
        expected_source_after = {
            f"sourceAfter:{index:04d}": _path_hash_for_binding(path)
            for index, path in enumerate(expected_sources)
        }
        expected_output_hashes = {
            f"output:{index:04d}": _path_hash_for_binding(path)
            for index, path in enumerate(expected_outputs)
        }
        before = record.get("filesBefore")
        after = record.get("filesAfter")
        if not isinstance(before, list) or not isinstance(after, list):
            raise ValueError("invalid-attestation-file-observations")
        observed_before = {item.get("role"): item.get("pathSha256") for item in before
                           if isinstance(item, dict)}
        observed_after = {item.get("role"): item.get("pathSha256") for item in after
                          if isinstance(item, dict)}
        expected_before_roles = {"adapter", "attestationModule", "pythonRuntime", "compiler",
                                 "wineLauncher", *expected_source_hashes}
        expected_after_roles = set(expected_source_after) | set(expected_output_hashes)
        if (len(observed_before) != len(before) or len(observed_after) != len(after)
                or set(observed_before) != expected_before_roles
                or set(observed_after) != expected_after_roles
                or any(observed_before.get(role) != digest
                       for role, digest in expected_source_hashes.items())
                or any(observed_after.get(role) != digest
                       for role, digest in {**expected_source_after, **expected_output_hashes}.items())):
            raise ValueError("attestation-path-role-binding-mismatch")

        def file_projection(rows):
            projected = []
            for item in rows:
                if not isinstance(item, dict):
                    raise ValueError("invalid-attestation-file-row")
                role, path_hash = item.get("role"), item.get("pathSha256")
                if not isinstance(role, str) or not re.fullmatch(
                        r"(?:adapter|attestationModule|pythonRuntime|compiler|wineLauncher|source:\d{4}|sourceAfter:\d{4}|output:\d{4})", role):
                    raise ValueError("invalid-attestation-file-role")
                safe = {"role": role,
                        "pathSha256": path_hash if isinstance(path_hash, str)
                            and re.fullmatch(r"[0-9a-f]{64}", path_hash) else None,
                        "observed": item.get("observed") is True,
                        "size": item.get("size") if type(item.get("size")) is int
                            and 0 <= item.get("size") <= 128 * 1024 * 1024 else None,
                        "sha256": item.get("sha256") if isinstance(item.get("sha256"), str)
                            and re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) else None,
                        "stableDuringObservation": item.get("stableDuringObservation") is True}
                projected.append(safe)
            return projected

        canonical = _canonical_json_bytes(record)
        sanitized = {
            "schema": _COMPILER_ATTESTATION_SCHEMA,
            "complete": False,
            "argvSha256": record["argvSha256"],
            "argvCount": record["argvCount"],
            "environmentSha256": environment_record["sha256"],
            "processReturnCode": process_record.get("adapterObservedReturnCode"),
            "durationNs": process_record["durationNs"],
            "filesBefore": file_projection(before),
            "filesAfter": file_projection(after),
            "fileHashesEnabled": record["fileHashesEnabled"],
            "unknownCount": len(record["unknowns"]) if isinstance(record["unknowns"], list) else None,
        }
        return {"status": "adapter-reported-unbound",
                "schema": _COMPILER_ATTESTATION_SCHEMA,
                "attestationSha256": claimed_digest,
                "canonicalSha256": _digest(canonical),
                "record": sanitized, "originAuthenticated": False,
                "pathRolesMatched": True,
                "returnCodeMatched": process_returncode is not None,
                "diagnosticOnly": True, "complete": False}
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"status": "marker-malformed", "reason": reason[:120],
                "diagnosticOnly": True, "complete": False}


def _bind_compiler_run_attestation(result: dict, stderr: str | bytes | None,
                                   binding: dict | None = None,
                                   *, attestation: dict | None = None,
                                   sources: list[Path] | None = None,
                                   outputs: list[Path] | None = None,
                                   process_returncode: int | None = None,
                                   launch_state: str = "unknown") -> dict:
    result["compilerRunAttestation"] = (attestation if attestation is not None
                                         else _compiler_run_attestation(
                                             stderr, sources=sources, outputs=outputs,
                                             process_returncode=process_returncode))
    if binding is not None:
        result["compilerRunBinding"] = {**binding, "diagnosticOnly": True,
                                        "launchState": launch_state,
                                        "independentPerFunctionInvocation": (
                                            binding.get("scope") == "single-translation-unit"
                                            if launch_state != "not-started" else None)}
    return result


def _shared_attestation_reference(attestation: dict, group_id: str, index: int) -> dict:
    """Reference a single group record from each non-owner batch row."""
    return {"status": "shared-group-reference",
            "attestationSha256": attestation.get("attestationSha256"),
            "groupId": group_id, "ownerSourceIndex": 0, "sourceIndex": index,
            "diagnosticOnly": True, "originAuthenticated": False, "complete": False}


def _candidate_address(path: Path) -> int | None:
    """Resolve an address only from an unambiguous recovered-source header."""
    try:
        with path.open("rb") as candidate:
            source = candidate.read(800).decode("utf-8", errors="strict")
    except (OSError, UnicodeError):
        return None
    header_addresses = {int(value, 16) for value in _ADDR_RE.findall(source)}
    named_addresses = {int(value, 16) for value in _NAMEADDR_RE.findall(source)}
    if len(header_addresses) > 1 or len(named_addresses) > 1:
        return None
    if header_addresses and named_addresses and header_addresses != named_addresses:
        return None
    addresses = header_addresses or named_addresses
    return next(iter(addresses)) if len(addresses) == 1 else None


def _select_candidates(ap: argparse.ArgumentParser, selectors: list[str],
                       ranked_files: list[tuple[bool, str, Path, tuple[int, int, int, int, int]]]
                       ) -> tuple[list[Path], list[dict]]:
    """Resolve exact inventory basenames or unique recovered-source addresses."""
    by_name = {name: path for _, name, path, _ in ranked_files}
    address_matches: dict[int, list[Path]] = {}
    candidate_addresses: dict[str, int | None] = {}
    address_selectors: dict[str, int] = {}
    for selector in selectors:
        if not selector or Path(selector).name != selector or "/" in selector or "\\" in selector:
            ap.error(f"unsafe --candidate value (expected an exact C/C++ basename or hex address): {selector!r}")
        if selector not in by_name:
            match = _ADDRESS_SELECTOR_RE.fullmatch(selector)
            if match is None:
                ap.error(f"unknown --candidate value: {selector!r}")
            address_selectors[selector] = int(match.group(1), 16)
    if address_selectors:
        for _, name, path, _ in ranked_files:
            address = _candidate_address(path)
            candidate_addresses[name] = address
            if address is not None:
                address_matches.setdefault(address, []).append(path)

    selected: list[Path] = []
    resolved: list[dict] = []
    seen: set[str] = set()
    for selector in selectors:
        if selector in by_name:
            path = by_name[selector]
            kind = "basename"
            address = candidate_addresses.get(path.name)
            if path.name not in candidate_addresses:
                address = _candidate_address(path)
        else:
            address = address_selectors[selector]
            matches = address_matches.get(address, [])
            if not matches:
                ap.error(f"--candidate address does not resolve in verified-dir: {selector!r}")
            if len(matches) != 1:
                ap.error(f"--candidate address is ambiguous in verified-dir: {selector!r}")
            path = matches[0]
            kind = "address"
        if path.suffix.lower() not in SOURCE_LANGUAGES or path.name.startswith(".agentdecompile-"):
            ap.error(f"--candidate does not identify a verifier source: {selector!r}")
        if path.name in seen:
            ap.error(f"duplicate --candidate selection resolves to {path.name!r}")
        seen.add(path.name)
        selected.append(path)
        resolved.append({"identifier": selector, "kind": kind, "file": path.name,
                         "address": hex(address) if address is not None else None})
    return selected, resolved


def file_region_offset(raw: bytes, address: int, size: int) -> int | None:
    """Resolve a whole region inside exactly one file-backed PE section.

    Virtual-only bytes, raw padding outside the mapped virtual extent,
    cross-section regions, malformed section tables and ambiguous overlaps do
    not describe bytes observed from the requested virtual address.
    """
    try:
        if raw[:2] != b"MZ" or type(address) is not int or type(size) is not int or size <= 0:
            return None
        pe = struct.unpack_from("<I", raw, 0x3C)[0]
        if raw[pe:pe + 4] != b"PE\0\0":
            return None
        count = struct.unpack_from("<H", raw, pe + 6)[0]
        optional_size = struct.unpack_from("<H", raw, pe + 20)[0]
        optional = pe + 24
        magic = struct.unpack_from("<H", raw, optional)[0]
        if magic == 0x10B and optional_size >= 32:
            image_base = struct.unpack_from("<I", raw, optional + 28)[0]
        elif magic == 0x20B and optional_size >= 32:
            image_base = struct.unpack_from("<Q", raw, optional + 24)[0]
        else:
            return None
        sections = optional + optional_size
        if sections + count * 40 > len(raw):
            return None
        matches = []
        overlaps = 0
        request_end = address + size
        for index in range(count):
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from(
                "<IIII", raw, sections + index * 40 + 8
            )
            delta = address - image_base - rva
            backed_size = min(virtual_size, raw_size)
            section_start = image_base + rva
            section_end = section_start + backed_size
            if (raw_offset + raw_size <= len(raw)
                    and max(address, section_start) < min(request_end, section_end)):
                overlaps += 1
            if (0 <= delta and delta + size <= backed_size
                    and raw_offset + raw_size <= len(raw)):
                matches.append(raw_offset + delta)
        return matches[0] if len(matches) == 1 and overlaps == 1 else None
    except (ValueError, struct.error):
        return None


def pe_mapper(blob: bytes):
    """Return a whole-region VA mapper bound to one captured PE snapshot."""
    return lambda address, size: file_region_offset(blob, address, size)


def text_bytes_and_relocs(obj: bytes, *, strict: bool = False) -> tuple[bytes, list[int]] | None:
    """Extract one unambiguous code body without guessing a C++ extent.

    Default callers retain tuple-or-None behavior. Verification requests strict
    refusal diagnostics. A COMDAT primary body is admitted only when one external
    function symbol and its compiler-emitted FPO extent identify it, and every
    other code section is associated with that primary. This excludes cleanup
    funclets from the primary comparison; it does not select a linker winner.
    Four-byte relocation masking remains diagnostic, not linker semantics.
    """
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    try:
        inventory = parse_object_inventory(obj)
        machine = inventory['machine']
        require(inventory['characteristics'] == 0, 'unsupported-coff-header')
        require(inventory['symbolCount'] or inventory['symbolOffset'] == 0,
                'invalid-coff-symbol-table')
        code = []
        for section in inventory['sections']:
            name, characteristics = section['name'], section['characteristics']
            is_code = bool(characteristics & 0x20) or name.startswith('.text')
            if is_code and section['size']:
                require(section['rawHeader'][:8].rstrip(b'\0').startswith(b'.text')
                        and characteristics & 0x20000000,
                        'unsupported-coff-code-section')
                code.append(section)
        comdat_code = [item for item in code if item['characteristics'] & 0x1000]
        if comdat_code:
            function_symbols = [symbol for symbol in inventory['symbols'].values()
                                if symbol['section'] in {item['index'] for item in code}
                                and symbol['storageClass'] == 2
                                and symbol['type'] & 0x30 == 0x20]
            require(len(function_symbols) == 1,
                    'unsupported-coff-comdat-function-extent')
            symbol = function_symbols[0]
            try:
                extents = coff_object.compiler_function_extents(obj)['records']
            except (ValueError, struct.error, IndexError) as error:
                raise ValueError('unsupported-coff-comdat-function-extent') from error
            selected = [record for record in extents
                        if record['symbolIndex'] == symbol['index']]
            require(len(selected) == 1,
                    'unsupported-coff-comdat-function-extent')
            extent = selected[0]
            section = inventory['sections'][symbol['section'] - 1]
            start, end = extent['offset'], extent['offset'] + extent['size']
            require(section['characteristics'] & 0x1000
                    and extent['section'] == symbol['section']
                    and start == symbol['value'] and start < end <= section['size'],
                    'unsupported-coff-comdat-function-extent')

            # Associated code contributions may contain compiler-generated
            # funclets, but an unrelated COMDAT or ordinary .text contribution
            # makes this object ambiguous for a single-function comparison.
            definitions = inventory['sectionDefinitions']
            for item in code:
                root = item['index']
                visited = set()
                while (root in definitions and definitions[root]['selection'] == 5):
                    require(root not in visited,
                            'unsupported-coff-comdat-function-extent')
                    visited.add(root)
                    root = definitions[root]['association']
                require(root == section['index'],
                        'unsupported-coff-comdat-function-extent')

            offsets = []
            supported = ({0x6, 0x7, 0xb, 0x14} if machine == 0x14c else
                         {0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xb})
            for relocation in section['relocations']:
                operand, width = relocation['offset'], relocation['operandWidth']
                if operand >= end or (width is not None and operand + width <= start):
                    continue
                require(relocation['type'] in supported and width == 4
                        and relocation['symbolBinding'] == 'primary'
                        and start <= operand and operand + width <= end,
                        'unsupported-or-invalid-coff-relocation')
                offsets.append(operand - start)
            ordered = sorted(offsets)
            require(all(left + 4 <= right for left, right in zip(ordered, ordered[1:])),
                    'overlapping-coff-relocation-operands')
            return section['data'][start:end], offsets
        require(len(code) == 1, 'ambiguous-or-missing-coff-code-section')
        section = code[0]
        offsets = []
        # Only relocations whose encoded operand is four bytes are maskable.
        supported = {0x6, 0x7, 0xb, 0x14} if machine == 0x14c else {0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xb}
        for relocation in section['relocations']:
            operand = relocation['offset']
            require(relocation['type'] in supported and relocation['operandWidth'] == 4
                    and relocation['symbolBinding'] == 'primary',
                    'unsupported-or-invalid-coff-relocation')
            offsets.append(operand)
        ordered = sorted(offsets)
        require(all(left + 4 <= right for left, right in zip(ordered, ordered[1:])),
                'overlapping-coff-relocation-operands')
        return section['data'], offsets
    except (ValueError, struct.error, IndexError):
        if strict:
            raise
        return None


def _primary_emission_comparison(obj: bytes, target: bytes) -> dict:
    """Compare one independently FPO-bound primary without accepting closure.

    Positive external function identity must be unique in the emitted object.
    Cleanup funclets and associated data remain outside this primary comparison;
    neither an equal range nor masked operands select a COMDAT/linker winner.
    This pure path also consumes retained objects without another compilation.
    """
    if not isinstance(target, bytes) or not 0 < len(target) <= 64 * 1024**2:
        raise ValueError('primary-emission-target-region-capacity')
    inventory = parse_object_inventory(obj)
    candidates = [symbol for symbol in inventory['symbols'].values()
                  if symbol['section'] > 0 and symbol['storageClass'] == 2
                  and symbol['type'] & 0x30 == 0x20]
    if len(candidates) != 1:
        raise ValueError('primary-emission-symbol-ambiguous-or-missing')
    symbol = candidates[0]
    extents = coff_object.compiler_function_extents(obj)
    selected = [record for record in extents['records']
                if record['symbolIndex'] == symbol['index']]
    if len(selected) != 1:
        raise ValueError('primary-emission-fpo-ambiguous-or-missing')
    extent = selected[0]
    section = inventory['sections'][symbol['section'] - 1]
    start, size = extent['offset'], extent['size']
    if (extent['section'] != symbol['section'] or start != symbol['value']
            or not section['characteristics'] & 0x20
            or not section['characteristics'] & 0x20000000):
        raise ValueError('primary-emission-symbol-extent-disagreement')
    end = start + size
    offsets, relocation_preview = [], []
    supported = {0x6, 0x7, 0xb, 0x14} if inventory['machine'] == 0x14c else {
        0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xb}
    for relocation in section['relocations']:
        operand, width = relocation['offset'], relocation['operandWidth']
        if operand >= end or (width is not None and operand + width <= start):
            continue
        if (relocation['type'] not in supported or width != 4
                or relocation['symbolBinding'] != 'primary'
                or operand < start or operand + width > end):
            raise ValueError('primary-emission-relocation-unqualified')
        offset = operand - start
        offsets.append(offset)
        if len(relocation_preview) < 64:
            relocation_preview.append({'offset': offset, 'type': relocation['type'],
                                       'symbolIndex': relocation['symbolIndex']})
    offsets.sort()
    if any(left + 4 > right for left, right in zip(offsets, offsets[1:])):
        raise ValueError('primary-emission-relocation-overlap')
    text = section['data'][start:end]
    if len(text) != size:
        raise ValueError('primary-emission-range-unavailable')
    diff = masked_diff_count(text, target, offsets)
    mask = {index for offset in offsets for index in range(offset, offset + 4)}
    mismatches = []
    mismatch_count = 0
    for offset in range(max(len(text), len(target))):
        compiled = text[offset] if offset < len(text) else None
        original = target[offset] if offset < len(target) else None
        if compiled == original or (compiled is not None and original is not None and offset in mask):
            continue
        mismatch_count += 1
        if len(mismatches) < 64:
            mismatches.append({'offset': offset, 'compiledByte': compiled,
                               'targetByte': original})
    return {'diagnosticOnly': True, 'ok': False, 'accepted': False,
            'byteVerified': False, 'wholeImageVerified': False,
            'comparisonScope': 'compiler-emitted-primary-function',
            'primaryExtent': extent, 'primarySymbol': symbol['name'][:512],
            'primarySymbolTruncated': len(symbol['name']) > 512,
            'objectSha256': inventory['sha256'], 'targetRegionSha256': _digest(target),
            'compiledSize': size, 'targetSize': len(target), 'diff': diff,
            'rawEqual': text == target, 'maskedEqual': diff == 0,
            'relocs': len(offsets), 'relocationPreview': relocation_preview,
            'relocationPreviewTruncated': len(offsets) > 64,
            'mismatchPreview': mismatches, 'mismatchPreviewTruncated': mismatch_count > 64,
            'closureQualified': False, 'comdatSelectionVerified': False,
            'reason': 'primary-emission-mismatch' if diff else 'primary-emission-equal-closure-unqualified'}


def _compiler_extent_summary(obj: bytes, symbol_index: int | None = None) -> dict:
    """Bounded compiler-side extent evidence, never target/link acceptance."""
    try:
        observation = coff_object.compiler_function_extents(obj)
        records = observation['records']
        selected = [record for record in records if record['symbolIndex'] == symbol_index]
        return {'objectExtentSchema': observation['schema'],
                'objectExtentClaim': observation['claim'],
                'objectExtentRecordCount': len(records),
                'objectExtentRecords': records[:64],
                'objectExtentPreviewTruncated': len(records) > 64,
                'selectedExtentRecord': selected[0] if len(selected) == 1 else None}
    except ValueError as error:
        return {'objectExtentRecordCount': 0, 'objectExtentRecords': [],
                'objectExtentError': str(error)[:500],
                'objectExtentClaim': 'Compiler extent unqualified; no linked or target proof.'}


def _coff_section_summary(obj: bytes) -> dict:
    try:
        inventory = parse_object_inventory(obj)
    except ValueError as error:
        return {"objectBytes": len(obj), "objectSections": [],
                "objectInventoryError": str(error)}
    # Diagnostic JSON is a preview, not the inventory itself. Shared long names
    # are cheap in memory but repeated JSON strings must remain bounded too.
    preview = inventory['sections'][:64]
    functions = [symbol for symbol in inventory['symbols'].values()
                 if symbol['section'] > 0 and symbol['type'] == 0x20]
    contributions = []
    relocation_budget = 64
    for section in preview:
        definition = inventory['sectionDefinitions'].get(section['index'], {})
        relocations = []
        for relocation in section['relocations'][:relocation_budget]:
            symbol = (inventory['symbols'].get(relocation['symbolIndex'])
                      if relocation['symbolBinding'] == 'primary' else None)
            relocations.append({
                'offset': relocation['offset'], 'type': relocation['type'],
                'symbolIndex': relocation['symbolIndex'],
                'symbolName': symbol['name'][:512] if symbol else None,
                'symbolNameTruncated': bool(symbol and len(symbol['name']) > 512),
                'symbolSection': symbol['section'] if symbol else None,
                'symbolOffset': symbol['value'] if symbol else None,
                'symbolBinding': relocation['symbolBinding'],
                'operandWidth': relocation['operandWidth'],
                'addendHex': relocation['addendBytes'].hex()
                    if relocation['addendBytes'] is not None else None,
                'fixupSupported': relocation['fixupSupported']})
        relocation_budget -= len(relocations)
        contributions.append({
            'section': section['index'], 'name': section['name'][:512],
            'nameTruncated': len(section['name']) > 512,
            'size': section['size'], 'sha256': section['sha256'],
            'rawDataBytes': len(section['data']), 'hashScope': 'raw-section-data',
            'characteristics': section['characteristics'],
            'comdatSelection': definition.get('selection', 0),
            'associatedSection': definition.get('association')
                if definition.get('selection') == 5 else None,
            'relocationCount': section['relocationCount'],
            'relocations': relocations,
            'relocationPreviewTruncated': len(relocations) < section['relocationCount']})
    return {**_compiler_extent_summary(obj),
            "objectBytes": len(obj), "objectMachine": inventory['machine'],
            "objectSectionCount": inventory['sectionCount'],
            "objectSections": [section['name'][:512] for section in preview],
            "objectSectionPreviewTruncated": len(preview) < inventory['sectionCount']
                or any(len(section['name']) > 512 for section in preview),
            "objectInventorySchema": inventory['schema'],
            "objectContributions": contributions,
            "objectContributionClaim": "Section inventory only; not function extents, linked closure or byte proof.",
            "objectSha256": inventory['sha256'],
            "objectSymbolCount": inventory['symbolCount'],
            "objectFunctionSymbolCount": len(functions),
            "objectFunctionSymbols": [
                {'index': symbol['index'], 'name': symbol['name'][:512],
                 'section': symbol['section'], 'offset': symbol['value'],
                 'storageClass': symbol['storageClass'],
                 'auxiliaryCount': len(symbol['auxiliaries']),
                 'nameTruncated': len(symbol['name']) > 512}
                for symbol in functions[:64]],
            "objectFunctionPreviewTruncated": len(functions) > 64,
            "objectComdatSections": [section for section, definition
                                     in inventory['sectionDefinitions'].items()
                                     if definition['selection']]}


def masked_diff_count(cand: bytes, target: bytes, reloc_offsets: list[int]) -> int:
    """Diagnostic distance after masking operands; unequal lengths never match.

    A small nonzero count (1-5) is a near-miss the permuter can usually close in
    seconds; a large count means the recovered C is structurally different and
    belongs to the slow tier. Returning the distance (not just a bool) lets the
    finish pipeline rank the remainder and permute near-misses first.
    """
    n = min(len(cand), len(target))
    a, b = bytearray(cand[:n]), bytearray(target[:n])
    for o in reloc_offsets:
        if type(o) is not int or o < 0 or o + 4 > len(cand):
            raise ValueError("Invalid relocation operand range")
        for i in range(o, min(o + 4, n)):
            a[i] = 0
            b[i] = 0
    return abs(len(cand) - len(target)) + sum(a[i] != b[i] for i in range(n))


def masked_equal(cand: bytes, target: bytes, reloc_offsets: list[int]) -> bool:
    return masked_diff_count(cand, target, reloc_offsets) == 0


def _parse(src: str, raw: bytes, mapper, size_map: dict[int, int] | None = None) -> tuple[int, int, bytes] | None:
    """Return (addr, size, target_bytes). Handles multiple pool formats.

    ``size_map`` (addr -> size, from the func DB) supplies the size for
    candidate pools whose header carries an ``address:`` but no ``size:`` field
    (ghidra_bulk's whole-program candidates name the function e.g. ``return_void``
    and omit size). Without it those pools all fail to parse.
    """
    ma = _ADDR_RE.search(src)
    named = _NAMEADDR_RE.search(src)
    addr = int(ma.group(1), 16) if ma else (int(named.group(1), 16) if named else None)
    if addr is None:
        return None
    ms, mc = _SIZE_RE.search(src), _MC_RE.search(src)
    try:
        embedded = bytes.fromhex(mc.group(1)) if mc else None
        sizes = [int(ms.group(1))] if ms else []
        if embedded is not None:
            sizes.append(len(embedded))
        if size_map and addr in size_map:
            sizes.append(size_map[addr])
        if not sizes or any(type(size) is not int or size <= 0 or size != sizes[0] for size in sizes):
            return None
        size = sizes[0]
        offset = mapper(addr, size)
        if type(offset) is not int or offset < 0 or size > len(raw) - offset:
            return None
        target = raw[offset:offset + size]
        if embedded is not None and embedded != target:
            return None
        return addr, size, target
    except (ValueError, TypeError, OverflowError):
        return None


def _prepare_verification(cfile: Path, raw: bytes, mapper,
                          size_map: dict[int, int] | None = None,
                          source_text: str | None = None, source_bytes: bytes | None = None,
                          target_snapshot: dict | None = None):
    try:
        captured = source_bytes if source_bytes is not None else (source_text.encode("utf-8") if source_text is not None else cfile.read_bytes())
        src = captured.decode("utf-8", errors="strict")
    except (UnicodeError, OSError):
        return {"file": cfile.name, "ok": False, "rawEqual": False, "reason": "invalid-source-encoding"}
    evidence = {"sourcePath": str(cfile.resolve()), "sourceSha256": hashlib.sha256(captured).hexdigest(),
                "sourceLanguage": source_language(cfile),
                "comparisonPolicy": "raw-region-v1", "comparisonScope": "local-function"}
    # An asm-floor stub (__declspec(naked) + the original bytes) reproduces the
    # shipped bytes by construction -- it IS the original, not recovered C.
    # Counting it as byte-exact would launder the assembly floor into the
    # "decompiled" metric, so it is excluded here (and never emits a .bin).
    shim = _assembly_floor_reason(captured)
    if shim is not None:
        return {**evidence, "file": cfile.name, "ok": False,
                "reason": "asm-floor", "asm_floor": True,
                "sourceClaimDetail": shim}
    parsed = _parse(src, raw, mapper, size_map)
    if parsed is None:
        return {"file": cfile.name, "ok": False, "reason": "unparsed-header"}
    addr, size, target = parsed
    evidence['targetRegion'] = {'address': addr, 'offset': mapper(addr, size), 'size': size,
                                'sha256': hashlib.sha256(target).hexdigest()}
    if target_snapshot is not None:
        evidence['targetSnapshot'] = dict(target_snapshot)
    return src, evidence, addr, size, target


def _compare_compiled_object(cfile: Path, prepared: tuple, object_bytes: bytes,
                             bin_dir: Path | None = None,
                             maxc_dir: Path | None = None) -> dict:
    _, evidence, addr, size, target = prepared
    fname = "recovered"  # A single-section diagnostic, not symbol/extent proof.
    try:
        tr = text_bytes_and_relocs(object_bytes, strict=True)
    except (ValueError, struct.error, IndexError) as exc:
        if str(exc) in {'unsupported-coff-comdat-function-extent',
                        'ambiguous-or-missing-coff-code-section'}:
            try:
                comparison = _primary_emission_comparison(object_bytes, target)
                return {**evidence, 'file': cfile.name, 'addr': hex(addr),
                        **comparison, 'closureRefusal': str(exc)}
            except (ValueError, struct.error, IndexError) as primary_error:
                primary_refusal = str(primary_error)
        else:
            primary_refusal = None
        return {**evidence, 'file': cfile.name, 'addr': hex(addr), 'ok': False,
                'rawEqual': False, 'reason': 'invalid-compiler-object',
                'objectReadError': type(exc).__name__, 'detail': str(exc),
                'primaryComparisonRefusal': primary_refusal,
                **_coff_section_summary(object_bytes)}
    if tr is None:
        return {"file": cfile.name, "addr": hex(addr), "ok": False,
                "reason": "no-text-section", **_coff_section_summary(object_bytes)}
    text, reloc_offsets = tr
    try:
        diff = masked_diff_count(text, target, reloc_offsets)
    except ValueError:
        return {**evidence, "file": cfile.name, "addr": hex(addr), "ok": False,
                "rawEqual": False, "reason": "invalid-relocations"}
    byte_exact = diff == 0
    raw_equal = text == target
    # The normal substitution channel carries only the compiler's exact raw
    # region. A masked-only match remains useful in the receipt, but copying
    # target relocation operands would manufacture contribution-shaped bytes.
    if raw_equal and bin_dir is not None:
        (bin_dir / f"{addr:08x}.bin").write_bytes(text)
    # max-c substitution bytes: relocation operands are copied from the target
    # image, so this remains a diagnostic readable-C build, never exact proof.
    if maxc_dir is not None and len(text) >= size:
        mc = bytearray(text[:size])
        for offset in reloc_offsets:
            for index in range(offset, min(offset + 4, size)):
                mc[index] = target[index]
        (maxc_dir / f"{addr:08x}.bin").write_bytes(bytes(mc))
    return {**evidence, "file": cfile.name, "addr": hex(addr), "size": size, "func": fname,
            "rawEqual": raw_equal, "compiledSize": len(text), "maskedEqual": byte_exact,
            "relocs": len(reloc_offsets), "ok": byte_exact, "diff": diff,
            "reloc_linked": False,
            "reason": "byte-exact-relocation-masked" if byte_exact else "mismatch"}


def _compiler_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except OSError as exc:
        raise RuntimeError(f"could not verify private compiler process group {group_id}") from exc
    return True


def _wait_for_compiler_group_exit(group_id: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _compiler_group_exists(group_id):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))
    return True


def _signal_compiler_group(group_id: int, signum: int) -> None:
    try:
        os.killpg(group_id, signum)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise RuntimeError(f"could not signal private compiler process group {group_id}") from exc


def _compile_invocation(compiler: str, arguments: list[str], timeout: int = 180,
                        cleanup_seconds: float = 2.0,
                        environment: dict[str, str] | None = None):
    compiler_path = Path(compiler).resolve()
    command = ([sys.executable, str(compiler_path)] if compiler_path.suffix == ".py"
               else ["bash", str(compiler_path)])
    argv = [*command, *arguments]
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True, env=environment)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        # The process group is private to this launch. Wine and cl.exe inherit
        # it, so terminate only this invocation tree before a fallback can run.
        group_id = process.pid  # start_new_session=True makes this the private PGID.
        _signal_compiler_group(group_id, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=cleanup_seconds)
        except subprocess.TimeoutExpired:
            stdout = stderr = None
        # Pipe EOF is not proof that every descendant exited: a child may have
        # closed both pipes and kept running. Check the private group itself.
        if not _wait_for_compiler_group_exit(group_id, cleanup_seconds):
            _signal_compiler_group(group_id, signal.SIGKILL)
            try:
                stdout, stderr = process.communicate(timeout=max(cleanup_seconds, 1.0))
            except subprocess.TimeoutExpired:
                stdout = stderr = None
        try:
            process.wait(timeout=max(cleanup_seconds, 1.0))
        except subprocess.TimeoutExpired as reap_error:
            raise RuntimeError("compiler adapter could not be reaped after group termination") from reap_error
        if _compiler_group_exists(group_id):
            _signal_compiler_group(group_id, signal.SIGKILL)
            if not _wait_for_compiler_group_exit(group_id, max(cleanup_seconds, 1.0)):
                raise RuntimeError("private compiler process group remained alive after SIGKILL")
        if stdout is None or stderr is None:
            try:
                stdout, stderr = process.communicate(timeout=max(cleanup_seconds, 1.0))
            except subprocess.TimeoutExpired:
                pass
        if stdout is None or stderr is None:
            # A surviving process outside the invocation group may have kept an
            # inherited pipe open. Do not signal it or start a fallback.
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            raise RuntimeError("compiler output pipes remained open after its process group exited")
        # Retryable timeout reaches the caller only after the owned group is
        # empty and the adapter parent has been reaped.
        raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr) from timeout_error
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _retain_compiler_diagnostic(cfile: Path, prepared: tuple, compiler: str,
                                normalized: bytes, object_bytes: bytes | None,
                                result: dict, diagnostic: str = "") -> dict:
    """Keep invocation evidence, including successful emitted objects.

    Reservation accounting is committed before publication. Failed writes may
    consume reserved capacity, but cannot silently undercount it or evict work.
    Retention never grants exact/substitution or recovered-source authority.
    """
    import fcntl

    result['sourceLanguage'] = source_language(cfile)
    root = cfile.resolve().parent / '.compiler-diagnostics'
    maximum_bytes, maximum_entries = 4 * 1024**3, 50_000
    maximum_file = 64 * 1024**2
    stage = None
    try:
        if len(normalized) > maximum_file or (object_bytes is not None and len(object_bytes) > maximum_file):
            raise ValueError('Diagnostic input/object exceeds the 64 MiB per-file limit.')
        wrapper = Path(compiler).resolve()
        try:
            wrapper_digest = _file_digest(wrapper)
        except OSError:
            wrapper_digest = None
        metadata = {'schema': 'agentdecompile.compiler-diagnostic/v1',
            'claim': 'Preserved compiler evidence only; not verified recovery or a reusable success receipt.',
            'source': prepared[1], 'compilerAdapter': {'path': str(wrapper), 'sha256': wrapper_digest,
                'basisComplete': False, 'observedAfterInvocation': True,
                'scope': 'adapter file only; invocation-pinned transitive basis is recorded in targetSnapshot when available'},
            'normalizedInputSha256': _digest(normalized),
            'sourceLanguage': source_language(cfile),
            'frontendSelection': 'source suffix retained; MSVC adapter selects per-file /Tc or /Tp; transitive basis incomplete',
            'objectSha256': _digest(object_bytes) if object_bytes is not None else None,
            'invocation': ({'kind': 'batch', **{key: result['batchCompile'][key]
                for key in ('groupId', 'translationUnits') if key in result['batchCompile']}}
                if isinstance(result.get('batchCompile'), dict)
                else {'kind': 'batch', 'groupId': result['batchGroupId']} if result.get('batchGroupId')
                else {'kind': 'single-translation-unit'}),
            'compilerRunAttestation': result.get('compilerRunAttestation', {
                'status': 'marker-not-found', 'diagnosticOnly': True, 'complete': False}),
            'compilerRunBinding': result.get('compilerRunBinding'),
            'outcome': {k: result.get(k) for k in ('reason', 'rawEqual', 'maskedEqual', 'diff', 'compilerReturnCode')},
            'diagnostic': diagnostic[-65536:], 'diagnosticTruncated': len(diagnostic) > 65536,
            'compiles': None, 'byteVerified': False, 'wholeImageVerified': False}
        if object_bytes is not None:
            metadata['coff'] = _coff_section_summary(object_bytes)
            metadata['coff']['objectSections'] = metadata['coff'].get('objectSections', [])[:1024]
            try:
                extracted = text_bytes_and_relocs(object_bytes)
                if extracted is not None:
                    text, offsets = extracted
                    metadata['relocations'] = {'offsets': offsets[:16384], 'count': len(offsets),
                        'truncated': len(offsets) > 16384, 'textSha256': _digest(text),
                        'textBytes': len(text), 'semanticsVerified': False}
            except (ValueError, struct.error, IndexError) as exc:
                metadata['relocationReadError'] = type(exc).__name__
        content = json.dumps(metadata, sort_keys=True).encode('utf-8')
        if len(content) > 2 * 1024**2:
            raise ValueError('Diagnostic metadata exceeds the 2 MiB limit.')
        identifier = _digest(content)
        required = len(content) + len(normalized) + len(object_bytes or b'')
        root.mkdir(exist_ok=True)
        if root.is_symlink() or root.resolve() != root:
            raise ValueError('Diagnostic store must not be symlinked.')
        lock_path, ledger_path = root / '.lock', root / 'index.json'
        if lock_path.is_symlink() or ledger_path.is_symlink():
            raise ValueError('Diagnostic store control files must not be symlinked.')
        with lock_path.open('a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if ledger_path.exists():
                if ledger_path.stat().st_size > 4096:
                    raise ValueError('Diagnostic capacity index exceeds the 4 KiB limit.')
                ledger = json.loads(ledger_path.read_text())
                if (ledger.get('schema') != metadata['schema'] or type(ledger.get('bytes')) is not int
                        or ledger['bytes'] < 0 or type(ledger.get('count')) is not int or ledger['count'] < 0):
                    raise ValueError('Diagnostic index is invalid; existing evidence was not overwritten.')
            else:
                if any(path.name != '.lock' for path in root.iterdir()):
                    raise ValueError('Diagnostic store has unaccounted existing files; reconcile before writing.')
                ledger = {'schema': metadata['schema'], 'bytes': 0, 'count': 0}
            destination = root / identifier
            if destination.exists() or destination.is_symlink():
                if ledger['count'] < 1 or ledger['bytes'] < required:
                    raise ValueError('Existing diagnostic artifact is not covered by capacity accounting.')
                if destination.is_symlink() or not destination.is_dir():
                    raise ValueError('A diagnostic reservation exists without a published artifact.')
                for name, payload in [('input.c', normalized), ('manifest.json', content), *([('output.obj', object_bytes)] if object_bytes is not None else [])]:
                    path = destination / name
                    if path.is_symlink() or not path.is_file() or path.stat().st_size != len(payload) or _file_digest(path) != _digest(payload):
                        raise ValueError('An existing diagnostic artifact failed its digest check.')
            else:
                if ledger['count'] >= maximum_entries or ledger['bytes'] + required > maximum_bytes:
                    raise ValueError('Diagnostic store capacity or publication boundary prevents retention; no evidence was evicted.')
                ledger['count'] += 1
                ledger['bytes'] += required
                _write_json_atomic(ledger_path, ledger)
                stage = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
                for name, payload in [('input.c', normalized), ('manifest.json', content), *([('output.obj', object_bytes)] if object_bytes is not None else [])]:
                    with (stage / name).open('xb') as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                os.rename(stage, destination)
                stage = None
                descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        result['diagnosticRetention'] = {'ok': True, 'id': identifier, 'path': str(destination),
            'input': str(destination / 'input.c'), 'object': str(destination / 'output.obj') if object_bytes is not None else None,
            'manifest': str(destination / 'manifest.json'), 'byteVerified': False}
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        result['diagnosticRetention'] = {'ok': False, 'error': str(exc), 'store': str(root)}
        result['comparisonReason'] = result.get('reason')
        result['ok'] = False
        result['reason'] = 'diagnostic-retention-failed'
    finally:
        if stage is not None:
            shutil.rmtree(stage)
    return result


def _read_retained_emission(cfile: Path, reference: dict) -> tuple[dict, bytes, bytes]:
    """Read one content-addressed entry, without scanning or following links."""
    import stat

    identifier = reference.get('id')
    if reference.get('ok') is not True or not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{64}', identifier):
        raise ValueError('invalid-diagnostic-reference')
    root = cfile.resolve().parent / '.compiler-diagnostics'
    destination = root / identifier
    if reference.get('path') != str(destination):
        raise ValueError('diagnostic-reference-outside-source-pool')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_descriptor = os.open(root, directory_flags)
    try:
        entry_descriptor = os.open(identifier, directory_flags, dir_fd=root_descriptor)
        try:
            def read(name: str, maximum: int) -> bytes:
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=entry_descriptor)
                try:
                    before = os.fstat(descriptor)
                    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
                        raise ValueError('invalid-diagnostic-file')
                    with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                        data = stream.read(maximum + 1)
                    after = os.fstat(descriptor)
                    if (len(data) != before.st_size or any(getattr(before, key) != getattr(after, key)
                            for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))):
                        raise ValueError('diagnostic-file-changed-during-read')
                    return data
                finally:
                    os.close(descriptor)
            content = read('manifest.json', 2 * 1024**2)
            if _digest(content) != identifier:
                raise ValueError('diagnostic-manifest-digest-mismatch')
            manifest = json.loads(content)
            if not isinstance(manifest, dict) or manifest.get('schema') != 'agentdecompile.compiler-diagnostic/v1':
                raise ValueError('unsupported-diagnostic-schema')
            normalized = read('input.c', 64 * 1024**2)
            object_bytes = read('output.obj', 64 * 1024**2)
            if (_digest(normalized) != manifest.get('normalizedInputSha256')
                    or _digest(object_bytes) != manifest.get('objectSha256')):
                raise ValueError('diagnostic-payload-digest-mismatch')
            return manifest, normalized, object_bytes
        finally:
            os.close(entry_descriptor)
    finally:
        os.close(root_descriptor)


def replay_retained_compiler_diagnostic(cfile: Path, raw: bytes, mapper, compiler: str,
                                       reference: dict | None, size_map: dict[int, int] | None = None,
                                       source_bytes: bytes | None = None,
                                       target_snapshot: dict | None = None) -> dict:
    """Compare a preserved emission; never compile, publish or accept it.

    The caller owns the captured target snapshot, as for verify_one. V1 does
    not pin language, flags, environment or transitive compiler inputs. Exact
    normalized input and adapter identity only permit a historical diagnostic;
    even equality cannot replace the required current compiler invocation.
    """
    observation = {'ok': False, 'diagnosticOnly': True, 'freshCompilation': False,
        'reusedObject': False, 'byteVerified': False, 'wholeImageVerified': False,
        'compilerCompatibility': 'incomplete-v1-invocation-basis'}
    try:
        if not isinstance(reference, dict):
            raise ValueError('no-retained-object-reference')
        prepared = _prepare_verification(cfile, raw, mapper, size_map,
                                         source_bytes=source_bytes, target_snapshot=target_snapshot)
        if isinstance(prepared, dict):
            raise ValueError('current-target-or-source-unavailable:' + prepared['reason'])
        manifest, normalized, object_bytes = _read_retained_emission(cfile, reference)
        source = manifest.get('source')
        adapter = manifest.get('compilerAdapter')
        if (not isinstance(source, dict) or source.get('sourceSha256') != prepared[1]['sourceSha256']
                or not isinstance(source.get('sourcePath'), str)):
            raise ValueError('diagnostic-source-identity-mismatch')
        historical_snapshot = source.get('targetSnapshot')
        historical_policy = (historical_snapshot.get('compilerPolicy')
                             if isinstance(historical_snapshot, dict) else None)
        current_snapshot = prepared[1].get('targetSnapshot')
        current_policy = (current_snapshot.get('compilerPolicy')
                          if isinstance(current_snapshot, dict) else None)
        observation.update({'historicalCompilerPolicy': historical_policy,
                            'currentCompilerPolicy': current_policy,
                            'compilerPolicyMatches': current_policy is not None
                                and current_policy == historical_policy})
        # Old v1 writers always staged in.c; absence of language never supports
        # replay as native C++. It remains historical C diagnostic evidence.
        if manifest.get('sourceLanguage', 'c') != source_language(cfile):
            raise ValueError('diagnostic-source-language-changed-or-unbound')
        if normalized != _normalized_source(cfile, prepared[0]):
            raise ValueError('diagnostic-normalized-input-changed')
        if (not isinstance(adapter, dict) or not isinstance(adapter.get('path'), str)
                or adapter.get('sha256') != _file_digest(Path(compiler).resolve())):
            raise ValueError('diagnostic-compiler-adapter-changed')
        if manifest.get('invocation') != {'kind': 'single-translation-unit'}:
            raise ValueError('v1-batch-invocation-not-independently-bound')
        outcome = manifest.get('outcome')
        if (not isinstance(outcome, dict) or outcome.get('reason') not in {'mismatch', 'byte-exact-relocation-masked'}
                or outcome.get('compilerReturnCode') not in (None, 0)):
            raise ValueError('diagnostic-successful-emission-not-established')
        comparison = _compare_compiled_object(cfile, prepared, object_bytes)
        if comparison.get('reason') == 'invalid-compiler-object':
            raise ValueError('invalid-retained-object:' + comparison.get('detail', 'invalid-coff'))
        if comparison.get('reason') not in {'mismatch', 'byte-exact-relocation-masked'}:
            raise ValueError('retained-object-comparison-unavailable:' + str(comparison.get('reason')))
        observation.update({'reusedObject': True, 'reason': 'retained-object-compared',
            'sourceLanguage': source_language(cfile),
            'diagnosticId': reference['id'], 'objectSha256': manifest['objectSha256'],
            'originalSourcePath': source['sourcePath'], 'originalCompilerAdapter': adapter,
            'originalInvocation': manifest['invocation'], 'currentTargetRegion': prepared[1]['targetRegion'],
            'comparison': {key: comparison[key] for key in (
                'reason', 'rawEqual', 'maskedEqual', 'diff', 'compiledSize', 'size', 'relocs') if key in comparison},
            'claim': 'Fresh local comparison of historical emission; no fresh compile or accepted source proof.'})
    except (OSError, ValueError, TypeError, KeyError, struct.error, IndexError) as exc:
        observation.update({'reason': 'retained-object-replay-refused', 'detail': str(exc)[:500]})
    return observation


def replay_retained_placement(source: Path, diagnostic_id: str, binding_contract: Path | None = None,
                              raw_path: Path | None = None, entry_symbol: str | None = None) -> dict:
    """Digest-bound contribution diagnostics; never compile or accept source.

    Bindings default to target-derived constraints; an explicit contract is opt-in.
    Neither supplied nor derived provenance is certified symbol identity.
    Equality under that contract does not qualify types, compiler, function
    extent, SafeSEH or full-image linkage. No cache or substitution writes occur.
    """
    import stat
    from .coff_fixup_roundtrip import derive_section_bindings, place_sections

    result = {'ok': False, 'diagnosticOnly': True, 'freshCompilation': False,
              'byteVerified': False, 'wholeImageVerified': False}

    def read(path: Path, maximum: int) -> bytes:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
                raise ValueError('invalid-replay-input-file')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                data = stream.read(maximum + 1)
            after = os.fstat(descriptor)
            if len(data) != before.st_size or any(getattr(before, key) != getattr(after, key)
                    for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('replay-input-changed-during-read')
            return data
        finally:
            os.close(descriptor)

    try:
        source = source.expanduser().resolve()
        reference = {'ok': True, 'id': diagnostic_id,
                     'path': str(source.parent / '.compiler-diagnostics' / diagnostic_id)}
        manifest, normalized, obj = _read_retained_emission(source, reference)
        result['compilerExtentEvidence'] = _compiler_extent_summary(obj)
        current_source = read(source, 64 * 1024**2)
        historical = manifest.get('source') or {}
        if (historical.get('sourceSha256') != _digest(current_source)
                or manifest.get('sourceLanguage') != source_language(source)
                or normalized != _normalized_source(source, current_source.decode('utf-8'))):
            raise ValueError('placement-source-or-object-identity-mismatch')
        snapshot = historical.get('targetSnapshot') or {}
        target_path = raw_path if raw_path is not None else Path(str(snapshot.get('path') or ''))
        raw = read(target_path, 256 * 1024**2)
        if snapshot.get('sha256') != _digest(raw):
            raise ValueError('placement-target-identity-mismatch')
        mapper = pe_mapper(raw)
        pe = struct.unpack_from('<I', raw, 0x3c)[0]
        optional = pe + 24
        magic = struct.unpack_from('<H', raw, optional)[0]
        if raw[:2] != b'MZ' or raw[pe:pe + 4] != b'PE\0\0' or magic not in (0x10b, 0x20b):
            raise ValueError('unsupported-placement-target-image')
        object_machine = struct.unpack_from('<H', obj)[0]
        if (struct.unpack_from('<H', raw, pe + 4)[0] != object_machine
                or {0x14c: 0x10b, 0x8664: 0x20b}.get(object_machine) != magic):
            raise ValueError('placement-target-architecture-mismatch')
        image_base = struct.unpack_from('<I' if magic == 0x10b else '<Q', raw,
                                        optional + (28 if magic == 0x10b else 24))[0]

        def target_region(address: int, size: int) -> bytes:
            offset = mapper(address, size)
            if type(offset) is not int or offset < 0 or size > len(raw) - offset:
                raise ValueError('placement-target-region-unmapped')
            return raw[offset:offset + size]

        if binding_contract is None:
            inventory = parse_object_inventory(obj)
            candidates = [symbol for symbol in inventory['symbols'].values()
                          if symbol['section'] > 0 and symbol['storageClass'] == 2
                          and symbol['type'] & 0x30 == 0x20
                          and (entry_symbol is None or symbol['name'] == entry_symbol)]
            if len(candidates) != 1:
                raise ValueError('placement-entry-symbol-ambiguous-or-missing')
            entry = candidates[0]
            entry_section = inventory['sections'][entry['section'] - 1]
            if (not entry_section['characteristics'] & 0x20
                    or entry['value'] >= entry_section['size']):
                raise ValueError('placement-entry-symbol-not-in-code')
            region = historical.get('targetRegion') or {}
            address, size = region.get('address'), region.get('size')
            if (type(address) is not int or type(size) is not int or size <= 0
                    or region.get('sha256') != _digest(target_region(address, size))):
                raise ValueError('placement-entry-region-identity-mismatch')
            result['compilerExtentEvidence'] = _compiler_extent_summary(obj, entry['index'])
            try:
                result['primaryEmissionComparison'] = _primary_emission_comparison(
                    obj, target_region(address, size))
            except (ValueError, struct.error, IndexError) as primary_error:
                result['primaryEmissionComparison'] = {
                    'diagnosticOnly': True, 'ok': False,
                    'reason': str(primary_error)[:500]}
            emitted = result['compilerExtentEvidence'].get('selectedExtentRecord')
            agrees = bool(emitted and emitted['section'] == entry['section']
                          and emitted['offset'] == entry['value'])
            result['capturedEntryExtentAgreement'] = {
                'capturedSize': size, 'compilerExtentRecordCount': int(agrees),
                'emittedSize': emitted['size'] if agrees else None,
                'equal': agrees and emitted['size'] == size,
                'claim': 'Compiler-emitted size compared with captured region; not target symbol identity or linked contribution.'}
            derived = derive_section_bindings(obj, entry['section'], address - entry['value'],
                                             target_region, image_base=image_base)
            contract = {'schema': 'agentdecompile.coff-placement-contract/v1',
                'diagnosticId': diagnostic_id, 'objectSha256': _digest(obj),
                'sourceSha256': _digest(current_source), 'targetSha256': _digest(raw),
                'imageBase': image_base,
                'placements': [{'section': number, 'address': base,
                    'targetSha256': _digest(target_region(base, inventory['sections'][number - 1]['size'])),
                    'provenance': derived['sectionProvenance'][number]}
                    for number, base in sorted(derived['placements'].items())],
                'externals': [{'name': name, 'address': base,
                    'provenance': derived['externalProvenance'][name]}
                    for name, base in sorted(derived['externals'].items())],
                'limitations': [
                    'Bindings are inferred from captured target operands, not independent symbol identity.',
                    'Section contributions do not establish function extents or COMDAT selection.',
                    'Segment-relative pseudo-symbols may be inferred; no ABI or ordinary image-global identity is certified.',
                    'Unreferenced metadata, SafeSEH, linked closure and whole-image reconstruction remain unqualified.',
                    'Historical emission only; no fresh compiler or source acceptance.']}
            chunks, encoded_size = [], 0
            for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':')).iterencode(contract):
                encoded = chunk.encode('utf-8')
                encoded_size += len(encoded)
                if encoded_size > 2 * 1024**2:
                    raise ValueError('derived-placement-contract-capacity-exceeded')
                chunks.append(encoded)
            content = b''.join(chunks)
            result.update({'bindingMode': 'target-derived', 'entrySymbol': entry['name'][:512],
                           'entrySymbolTruncated': len(entry['name']) > 512,
                           'independentBindingEvidence': False})
        else:
            if entry_symbol is not None:
                raise ValueError('entry-symbol-only-applies-to-derived-bindings')
            content = read(binding_contract, 2 * 1024**2)
            contract = json.loads(content)
            result['bindingMode'] = 'declared-contract'
        if not isinstance(contract, dict) or contract.get('schema') != 'agentdecompile.coff-placement-contract/v1':
            raise ValueError('unsupported-placement-contract')
        if (contract.get('diagnosticId') != diagnostic_id
                or contract.get('objectSha256') != _digest(obj)
                or contract.get('sourceSha256') != _digest(current_source)):
            raise ValueError('placement-source-or-object-identity-mismatch')
        if contract.get('targetSha256') != _digest(raw):
            raise ValueError('placement-target-identity-mismatch')
        if type(contract.get('imageBase')) is not int or contract['imageBase'] != image_base:
            raise ValueError('placement-image-base-mismatch')
        entries, external_entries = contract.get('placements'), contract.get('externals')
        limitations = contract.get('limitations')
        if (not isinstance(limitations, list) or not 0 < len(limitations) <= 64
                or any(not isinstance(item, str) or not item.strip() for item in limitations)):
            raise ValueError('placement-limitations-required')
        if not isinstance(entries, list) or not 0 < len(entries) <= 4096:
            raise ValueError('invalid-placement-entries')
        if not isinstance(external_entries, list) or len(external_entries) > 250_000:
            raise ValueError('invalid-external-entries')
        placements, bindings = {}, {}
        for entry in entries:
            if (not isinstance(entry, dict) or type(entry.get('section')) is not int
                    or type(entry.get('address')) is not int or entry['section'] in placements
                    or not isinstance(entry.get('provenance'), str) or not entry['provenance'].strip()):
                raise ValueError('invalid-or-duplicate-section-binding')
            placements[entry['section']] = entry['address']
            bindings[entry['section']] = entry
        externals = {}
        for entry in external_entries:
            if (not isinstance(entry, dict) or not isinstance(entry.get('name'), str)
                    or not entry['name'] or entry['name'] in externals
                    or type(entry.get('address')) is not int
                    or not isinstance(entry.get('provenance'), str) or not entry['provenance'].strip()):
                raise ValueError('invalid-or-duplicate-external-binding')
            externals[entry['name']] = entry['address']
        placed = place_sections(obj, placements, externals, image_base=image_base)
        comparisons = []
        relocation_budget = 64
        compared_count = equal_count = relocation_count = 0
        for section in placed['sections']:
            data, address = section['data'], section['address']
            offset = mapper(address, len(data))
            if type(offset) is not int or offset < 0 or len(data) > len(raw) - offset:
                raise ValueError('placement-target-region-unmapped')
            target = raw[offset:offset + len(data)]
            if bindings[section['section']].get('targetSha256') != _digest(target):
                raise ValueError('placement-region-identity-mismatch')
            compared_count += 1
            equal_count += data == target
            relocation_count += len(section['relocations'])
            if len(comparisons) >= 64:
                continue
            preview = [{**record, 'symbol': record['symbol'][:512],
                        'symbolTruncated': len(record['symbol']) > 512}
                       for record in section['relocations'][:relocation_budget]]
            relocation_budget -= len(preview)
            provenance = bindings[section['section']]['provenance']
            comparisons.append({'section': section['section'], 'name': section['name'][:512],
                'nameTruncated': len(section['name']) > 512,
                'address': address, 'size': len(data), 'targetSha256': _digest(target),
                'placedSha256': section['sha256'], 'equalUnderDeclaredBindings': data == target,
                'differingBytes': sum(a != b for a, b in zip(data, target)),
                'provenance': provenance[:1024], 'provenanceTruncated': len(provenance) > 1024,
                'relocationCount': len(section['relocations']),
                'relocations': preview,
                'relocationPreviewTruncated': len(preview) < len(section['relocations'])})
        result.update({'ok': True, 'reason': 'retained-contributions-compared',
            'diagnosticId': diagnostic_id, 'objectSha256': _digest(obj),
            'sourceSha256': _digest(current_source), 'targetSha256': _digest(raw),
            'contractSha256': _digest(content),
            'externals': [{'name': entry['name'][:512], 'address': entry['address'],
                          'nameTruncated': len(entry['name']) > 512,
                          'provenance': entry['provenance'][:1024],
                          'provenanceTruncated': len(entry['provenance']) > 1024}
                         for entry in external_entries[:64]],
            'externalCount': len(external_entries),
            'externalPreviewTruncated': len(external_entries) > 64,
            'sections': comparisons, 'unplacedSections': placed['unplacedSections'],
            'comparedSectionCount': compared_count, 'equalSectionCount': equal_count,
            'sectionPreviewTruncated': compared_count > len(comparisons),
            'relocationCount': relocation_count,
            'limitations': [item[:1024] for item in limitations],
            'limitationsTruncated': any(len(item) > 1024 for item in limitations),
            'claim': 'Historical emission under declared bindings only; no certified symbol identity, linked closure or source acceptance.'})
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error, IndexError) as exc:
        result.update({'reason': 'retained-placement-refused', 'detail': str(exc)[:500]})
    return result


def verify_one(cfile: Path, raw: bytes, mapper, compiler: str, size_map: dict[int, int] | None = None,
               bin_dir: Path | None = None, maxc_dir: Path | None = None,
               source_text: str | None = None, source_bytes: bytes | None = None,
               target_snapshot: dict | None = None,
               compiler_environment: dict[str, str] | None = None) -> dict:
    prepared = _prepare_verification(cfile, raw, mapper, size_map, source_text,
                                     source_bytes, target_snapshot)
    if isinstance(prepared, dict):
        return prepared
    src, _, addr, _, _ = prepared
    with tempfile.TemporaryDirectory(prefix="recon-") as td:
        cpath = Path(td) / ('in' + cfile.suffix.lower())
        opath = Path(td) / "out.obj"
        normalized = _normalized_source(cfile, src)
        cpath.write_bytes(normalized)
        fname = "recovered"  # Adapter label only; never a function-extent claim.
        single_binding = {"scope": "single-translation-unit", "sourceIndex": 0,
                          "outputIndex": 0, "sourceFile": cfile.name,
                          "sourceRole": "source:0000", "outputRole": "output:0000"}
        compile_started = time.monotonic()
        try:
            compile_result = _compile_invocation(compiler, [str(cpath), str(opath), fname],
                                                 environment=compiler_environment)
        except subprocess.TimeoutExpired as exc:
            result = {"file": cfile.name, "addr": hex(addr), "ok": False,
                    "reason": "compile-timeout",
                    "compileSeconds": round(time.monotonic() - compile_started, 3)}
            _bind_compiler_run_attestation(
                result, exc.stderr, single_binding, sources=[cpath], outputs=[opath],
                launch_state="timed-out")
            captured_stderr = exc.stderr.decode('utf-8', errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            diagnostic = captured_stderr or str(exc.output or '')
            return _retain_compiler_diagnostic(cfile, prepared, compiler, normalized,
                opath.read_bytes() if opath.is_file() else None, result, diagnostic)
        except OSError as exc:
            result = {'file': cfile.name, 'addr': hex(addr), 'ok': False,
                'reason': 'compile-failed', 'failureClass': 'compiler-launch-failure',
                'compileSeconds': round(time.monotonic() - compile_started, 3),
                'compilerDiagnostic': str(exc)[-2000:]}
            _bind_compiler_run_attestation(result, None, single_binding,
                                           launch_state="not-started")
            return _retain_compiler_diagnostic(cfile, prepared, compiler, normalized, None, result, str(exc))
        compile_seconds = round(time.monotonic() - compile_started, 3)
        result = {}
        _bind_compiler_run_attestation(
            result, compile_result.stderr, single_binding, sources=[cpath], outputs=[opath],
            process_returncode=compile_result.returncode, launch_state="completed")
        if compile_result.returncode != 0 or not opath.exists():
            # Keep the compiler's own bounded explanation in the receipt.  The
            # result remains a failed verification; this only makes the next
            # readable-C repair actionable without re-running the compiler.
            diagnostic = (compile_result.stderr or compile_result.stdout or "").strip()
            # Known MSVC source/type diagnostics are deterministic rejections.
            # Fatal/environment/resource errors and unknown compiler output remain
            # inconclusive, not semantic mismatches and not assumed transient.
            missing_temp_include = re.search(
                r"(?:fatal\s+)?error C1083\s*:\s*Cannot open include file:\s*['\"](/tmp/[^'\"]+)['\"]",
                diagnostic, re.IGNORECASE)
            deterministic = (
                re.search(r"\berror C[234]\d{3}\b", diagnostic, re.IGNORECASE) is not None
                or (missing_temp_include is not None
                    and not Path(missing_temp_include.group(1)).exists())
            )
            result.update({"file": cfile.name, "addr": hex(addr), "ok": False,
                    "reason": "compile-rejected" if deterministic else "compile-failed",
                    "failureClass": "deterministic-source-rejection" if deterministic else "unclassified-compiler-failure",
                    "compilerReturnCode": compile_result.returncode,
                    "compileSeconds": compile_seconds,
                    "compilerDiagnostic": diagnostic[-2000:]})
            return _retain_compiler_diagnostic(cfile, prepared, compiler, normalized,
                opath.read_bytes() if opath.is_file() else None, result, diagnostic)
        object_bytes = opath.read_bytes()
    try:
        result.update(_compare_compiled_object(cfile, prepared, object_bytes, bin_dir, maxc_dir))
    except (ValueError, struct.error, IndexError) as exc:
        result.update({**prepared[1], 'file': cfile.name, 'addr': hex(addr), 'ok': False,
            'reason': 'invalid-compiler-object', 'objectReadError': type(exc).__name__})
    result["compileSeconds"] = compile_seconds
    _retain_compiler_diagnostic(cfile, prepared, compiler, normalized, object_bytes,
        result, (compile_result.stderr or compile_result.stdout or '').strip())
    return result


def verify_batch(cfiles: list[Path], raw: bytes, mapper, compiler: str,
                 size_map: dict[int, int], bin_dirs: list[Path | None],
                 maxc_dirs: list[Path | None],
                 source_bytes_by_name: dict[str, bytes], target_snapshot: dict | None = None,
                 compiler_environment: dict[str, str] | None = None
                 ) -> list[dict]:
    """Compile 2-4 TUs together; attribute a failed batch only as far as needed."""
    if (not MIN_BATCH_TRANSLATION_UNITS <= len(cfiles) <= MAX_BATCH_TRANSLATION_UNITS
            or not _compiler_batch_capable(compiler)):
        results = []
        for index, path in enumerate(cfiles):
            started = time.monotonic()
            result = verify_one(path, raw, mapper, compiler, size_map, bin_dirs[index], maxc_dirs[index],
                                source_bytes=source_bytes_by_name[path.name], target_snapshot=target_snapshot,
                                compiler_environment=compiler_environment)
            result["candidateElapsedSeconds"] = round(time.monotonic() - started, 3)
            results.append(result)
        return results
    # A group ID names one concrete launch, not merely a repeatable list of
    # basenames. This prevents retries with changed source/target/toolchain
    # state from being conflated by downstream receipt consumers.
    group_id = uuid.uuid4().hex
    prepared = [_prepare_verification(path, raw, mapper, size_map,
                                      source_bytes=source_bytes_by_name[path.name],
                                      target_snapshot=target_snapshot) for path in cfiles]
    if any(isinstance(item, dict) for item in prepared):
        # A preflight-only source (for example an assembly-floor stub or a
        # malformed header) must not force every valid neighbor through a
        # separate Wine/MSVC startup. Resolve only those entries individually,
        # then retain batching for the prepared translation units.
        results_by_name = {}
        batch_files = []
        for index, (path, item) in enumerate(zip(cfiles, prepared, strict=True)):
            if not isinstance(item, dict):
                batch_files.append(path)
                continue
            started = time.monotonic()
            result = verify_one(
                path, raw, mapper, compiler, size_map,
                bin_dirs[index], maxc_dirs[index],
                source_bytes=source_bytes_by_name[path.name],
                target_snapshot=target_snapshot,
                compiler_environment=compiler_environment,
            )
            result["candidateElapsedSeconds"] = round(time.monotonic() - started, 3)
            results_by_name[path.name] = result
        if batch_files:
            batch_indices = [cfiles.index(path) for path in batch_files]
            batch_results = verify_batch(
                batch_files, raw, mapper, compiler, size_map,
                [bin_dirs[index] for index in batch_indices],
                [maxc_dirs[index] for index in batch_indices],
                source_bytes_by_name, target_snapshot, compiler_environment,
            )
            results_by_name.update(
                (path.name, result)
                for path, result in zip(batch_files, batch_results, strict=True)
            )
        return [results_by_name[path.name] for path in cfiles]

    fallback_reason = None
    fallback_diagnostic = ""
    batch_attestation = _compiler_run_attestation(None)
    with tempfile.TemporaryDirectory(prefix="recon-batch-") as td:
        root = Path(td)
        source_dir, object_dir = root / "sources", root / "objects"
        source_dir.mkdir()
        object_dir.mkdir()
        source_names = []
        object_paths = []
        for index, (path, item) in enumerate(zip(cfiles, prepared, strict=True)):
            src = item[0]
            name = f"unit_{index:02d}_{item[2]:08x}{path.suffix.lower()}"
            source_names.append(name)
            source_path = source_dir / name
            source_path.write_bytes(_normalized_source(path, src))
            object_paths.append(object_dir / (Path(name).stem + ".obj"))
        compile_started = time.monotonic()
        try:
            compile_result = _compile_invocation(
                compiler, ["--batch", str(source_dir), str(object_dir), *source_names],
                environment=compiler_environment)
            batch_stderr = compile_result.stderr
            # Parse the complete captured stream before reducing diagnostics.
            batch_attestation = _compiler_run_attestation(
                batch_stderr, sources=[source_dir / name for name in source_names],
                outputs=object_paths, process_returncode=compile_result.returncode)
            full_diagnostic = (batch_stderr or compile_result.stdout or "").strip()
            fallback_diagnostic = full_diagnostic[-2000:]
            if compile_result.returncode != 0:
                fallback_reason = "batch-compiler-nonzero"
            elif any(not path.is_file() or path.stat().st_size == 0 for path in object_paths):
                fallback_reason = "batch-object-mapping-ambiguous"
        except subprocess.TimeoutExpired as exc:
            fallback_reason = "batch-compiler-timeout"
            batch_stderr = exc.stderr
            batch_attestation = _compiler_run_attestation(
                batch_stderr, sources=[source_dir / name for name in source_names],
                outputs=object_paths)
            full_diagnostic = (batch_stderr.decode('utf-8', errors='replace')
                               if isinstance(batch_stderr, bytes) else (batch_stderr or ''))
            fallback_diagnostic = (full_diagnostic or str(exc))[-2000:]
        except OSError as exc:
            fallback_reason = "batch-compiler-unavailable"
            fallback_diagnostic = str(exc)[:2000]
        batch_seconds = round(time.monotonic() - compile_started, 3)
        if fallback_reason is None:
            results = []
            for index, (path, item, object_path) in enumerate(
                    zip(cfiles, prepared, object_paths, strict=True)):
                compare_started = time.monotonic()
                object_bytes = object_path.read_bytes()
                try:
                    result = _compare_compiled_object(path, item, object_bytes,
                                                      bin_dirs[index], maxc_dirs[index])
                except (ValueError, struct.error, IndexError) as exc:
                    result = {**item[1], 'file': path.name, 'addr': hex(item[2]), 'ok': False,
                        'reason': 'invalid-compiler-object', 'objectReadError': type(exc).__name__}
                result["comparisonSeconds"] = round(time.monotonic() - compare_started, 3)
                # The compiler wall time belongs to this group, not to each
                # function independently. Keep the one measured duration only
                # once so aggregate receipt consumers cannot double-count it.
                result.pop("compileSeconds", None)
                result["batchCompile"] = {
                    "groupId": group_id,
                    "translationUnits": len(cfiles),
                    "timingScope": "shared invocation; deduplicate by groupId, do not sum per source",
                    **({"invocationSeconds": batch_seconds} if index == 0 else {}),
                }
                _bind_compiler_run_attestation(result, None, {
                    "scope": "shared-batch", "groupId": group_id,
                    "sourceIndex": index, "outputIndex": index,
                    "sourceName": source_names[index],
                    "outputName": object_paths[index].name,
                    "translationUnits": len(cfiles),
                }, attestation=(batch_attestation if index == 0 else
                                _shared_attestation_reference(batch_attestation, group_id, index)),
                    launch_state="completed")
                _retain_compiler_diagnostic(path, item, compiler,
                    _normalized_source(path, item[0]), object_bytes,
                    result, (compile_result.stderr or compile_result.stdout or '').strip())
                results.append(result)
            return results

        retained_batch = []
        for index, (path, item, object_path) in enumerate(
                zip(cfiles, prepared, object_paths, strict=True)):
            observation = {'file': path.name, 'addr': hex(item[2]), 'ok': False,
                'reason': fallback_reason, 'batchGroupId': group_id,
                'sourceAttempted': fallback_reason != 'batch-compiler-unavailable'}
            _bind_compiler_run_attestation(observation, None, {
                "scope": "shared-batch", "groupId": group_id,
                "sourceIndex": index, "outputIndex": index,
                "sourceName": source_names[index],
                "outputName": object_paths[index].name,
                "translationUnits": len(cfiles),
            }, attestation=(batch_attestation if index == 0 else
                            _shared_attestation_reference(batch_attestation, group_id, index)),
                launch_state=("timed-out" if fallback_reason == "batch-compiler-timeout"
                              else "not-started" if fallback_reason == "batch-compiler-unavailable"
                              else "completed"))
            _retain_compiler_diagnostic(path, item, compiler,
                _normalized_source(path, item[0]),
                object_path.read_bytes() if object_path.is_file() else None,
                observation, fallback_diagnostic)
            retained_batch.append(observation)
        if any(observation.get('diagnosticRetention', {}).get('ok') is not True for observation in retained_batch):
            # Capacity/IO errors require attention, not another compiler launch.
            return retained_batch

    # A batch error cannot truthfully be attributed to one TU. Attribute it
    # sequentially, stopping at the first unexpected result so one shared
    # compiler failure does not trigger one identical retry per source.
    # An unavailable compiler cannot be attributed by launching it again.
    if fallback_reason == "batch-compiler-unavailable":
        first = {
            "file": cfiles[0].name,
            "ok": False,
            "reason": fallback_reason,
            "sourceAttempted": False,
            'diagnosticRetention': retained_batch[0]['diagnosticRetention'],
            "detail": fallback_diagnostic or "Compiler could not be launched.",
            "batchFallback": {
                "groupId": group_id,
                "reason": fallback_reason,
                "diagnostic": fallback_diagnostic,
                "timingScope": "shared failed invocation; do not sum per source",
                "initialInvocationSeconds": batch_seconds,
                "compilerRunAttestation": retained_batch[0].get("compilerRunAttestation"),
                "compilerRunBinding": retained_batch[0].get("compilerRunBinding"),
            },
        }
        results = [first]
        for path in cfiles[1:]:
            results.append({
                "file": path.name,
                "ok": False,
                "reason": "not-run-after-batch-fallback-failure",
                "sourceAttempted": False,
                'diagnosticRetention': retained_batch[len(results)]['diagnosticRetention'],
                "haltedBy": fallback_reason,
                "batchFallback": {"groupId": group_id, "reason": fallback_reason,
                    "compilerRunAttestation": retained_batch[len(results)].get("compilerRunAttestation"),
                    "compilerRunBinding": retained_batch[len(results)].get("compilerRunBinding")},
            })
        return results

    results = []
    for index, path in enumerate(cfiles):
        source_started = time.monotonic()
        result = verify_one(path, raw, mapper, compiler, size_map,
                            bin_dirs[index], maxc_dirs[index],
                            source_bytes=source_bytes_by_name[path.name], target_snapshot=target_snapshot,
                            compiler_environment=compiler_environment)
        result["candidateElapsedSeconds"] = round(time.monotonic() - source_started, 3)
        result["batchFallback"] = {
            "groupId": group_id, "reason": fallback_reason, "diagnostic": fallback_diagnostic,
            'diagnosticRetention': retained_batch[index]['diagnosticRetention'],
            "compilerRunAttestation": retained_batch[index].get("compilerRunAttestation"),
            "compilerRunBinding": retained_batch[index].get("compilerRunBinding"),
            "timingScope": "shared failed invocation; deduplicate by groupId, do not sum per source",
            **({"initialInvocationSeconds": batch_seconds} if index == 0 else {}),
        }
        results.append(result)
        signature = _failure_signature(result)
        if signature:
            for deferred_index, deferred in enumerate(cfiles[index + 1:], index + 1):
                results.append({
                    "file": deferred.name,
                    "ok": False,
                    "reason": "not-run-after-batch-fallback-failure",
                    "sourceAttempted": False,
                    "haltedBy": result.get("reason") or signature,
                    "batchFallback": {"groupId": group_id, "reason": fallback_reason,
                        "compilerRunAttestation": retained_batch[deferred_index].get("compilerRunAttestation"),
                        "compilerRunBinding": retained_batch[deferred_index].get("compilerRunBinding"),
                        'diagnosticRetention': retained_batch[deferred_index]['diagnosticRetention']},
                })
            break
    return results



CACHE_SCHEMA = "agentdecompile.byteexact-cache/v3"
# Cache against compile/comparison semantics and batching policy, which changes
# how the compiler invocation is formed. Unrelated scheduling, reporting, and
# checkpoint changes should not invalidate previously verified functions.
_COMPARISON_FUNCTIONS = (_normalized_source, source_language, _compiler_environment, file_region_offset, pe_mapper, text_bytes_and_relocs,
                         _primary_emission_comparison,
                         _coff_section_summary, masked_diff_count, _parse,
                         _prepare_verification, _compare_compiled_object,
                         _compile_invocation, verify_one, verify_batch,
                         _compiler_batch_capable, _verification_group_size,
                         _verification_group_limit)
_COMPARISON_POLICY = "\n".join(inspect.getsource(function)
                                 for function in _COMPARISON_FUNCTIONS)
_COMPARISON_POLICY += "\n" + "\n".join(
    pattern.pattern for pattern in (_ADDR_RE, _SIZE_RE, _FUNC_RE, _MC_RE, _NAMEADDR_RE)
)
_COMPARISON_POLICY += "\n" + json.dumps(_BATCH_POLICY, sort_keys=True)
_COMPARISON_POLICY += "\nsource-classification:" + hashlib.sha256(
    Path(source_claims.__file__).read_bytes()).hexdigest()
_COMPARISON_POLICY += "\ncoff-inventory:" + hashlib.sha256(
    Path(coff_object.__file__).read_bytes()).hexdigest()
_VERIFIER_REVISION = hashlib.sha256(_COMPARISON_POLICY.encode()).hexdigest()
_STABLE_REASONS = {"byte-exact-relocation-masked", "mismatch", "asm-floor", "unparsed-header", "compile-rejected"}

_EXPECTED_VERIFICATION_OUTCOMES = {
    "byte-exact-relocation-masked",
    "mismatch",
    "asm-floor",
}
_CANDIDATE_LOCAL_FAILURES = {
    "deterministic-source-rejection",
    "invalid-compiler-object",
    "invalid-relocations",
    "no-text-section",
    "unparsed-header",
    "invalid-source-encoding",
}


def _failure_signature(result: dict) -> str | None:
    """Stop on shared/compiler-state failures, not isolated candidate limits.

    Byte mismatches, deterministic source/compiler diagnostics, assembly-floor
    labels, preflight failures, and a single object's unsupported COFF/
    relocation shape are candidate-local. Preserve those receipts and keep the
    independent translation units moving. Unknown compiler/worker failures
    still halt dispatch to avoid repeating a potentially shared broken
    invocation across the rest of the lane.
    """
    reason = result.get("reason")
    failure_class = result.get("failureClass")
    if failure_class in _CANDIDATE_LOCAL_FAILURES:
        return None
    if reason in _EXPECTED_VERIFICATION_OUTCOMES or reason in _CANDIDATE_LOCAL_FAILURES:
        return None
    if reason is None:
        return None if result.get("ok") is True else "unclassified-verification-failure"
    diagnostic = result.get("compilerDiagnostic")
    if not isinstance(diagnostic, str) or not diagnostic.strip():
        detail = result.get("detail") or result.get("error")
        return f"{reason}: {detail}" if detail else str(reason)
    lines = [line for line in diagnostic.splitlines()
             if re.search(r"\b(?:fatal\s+)?error\b", line, re.IGNORECASE)]
    text = " ".join(lines or diagnostic.splitlines())
    text = re.sub(r"(?i)[A-Z]:[\\/](?:[^\s:]+[\\/])*[^\s:(]+\(\d+\)", "<source>", text)
    return re.sub(r"\s+", " ", text).strip().lower()[:512]


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_stamp(path: Path) -> tuple[int, int, int, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _candidate_entry(directory: Path, path: Path
                     ) -> tuple[bool, str, Path, tuple[int, int, int, int, int]]:
    """Validate and fingerprint one recovered source without enumerating its pool."""
    verified_root = directory.resolve()
    if path.is_symlink() or path.resolve().parent != verified_root or not path.is_file():
        raise OSError(f"verifier candidate is not a regular child of verified-dir: {path}")
    try:
        asm_floor = _candidate_is_assembly_floor(path)
    except OSError as exc:
        raise OSError(f"could not classify verifier candidate {path}: {exc}") from exc
    stamp = _file_stamp(path)
    if stamp is None:
        raise OSError(f"could not fingerprint verifier candidate {path}")
    return asm_floor, path.name, path, stamp


def _selected_candidate_stamps(directory: Path, paths: list[Path]
                               ) -> list[tuple[str, tuple[int, int, int, int, int]]]:
    """Recheck only selected sources, including their regular-child boundary."""
    verified_root = directory.resolve()
    current = []
    for path in paths:
        if path.is_symlink() or path.resolve().parent != verified_root or not path.is_file():
            raise OSError(f"verifier candidate is not a regular child of verified-dir: {path}")
        stamp = _file_stamp(path)
        if stamp is None:
            raise OSError(f"could not fingerprint verifier candidate {path}")
        current.append((path.name, stamp))
    return sorted(current)


def _candidate_inventory(directory: Path) -> list[tuple[bool, str, Path, tuple[int, int, int, int, int]]]:
    verified_root = directory.resolve()
    ranked = []
    for path in directory.iterdir():
        if path.suffix.lower() not in SOURCE_LANGUAGES:
            continue
        if path.name.startswith(".agentdecompile-"):
            continue
        if path.is_symlink() or path.resolve().parent != verified_root:
            raise OSError(f"verifier candidate is not a regular child of verified-dir: {path}")
        try:
            asm_floor = _candidate_is_assembly_floor(path)
        except OSError as exc:
            raise OSError(f"could not classify verifier candidate {path}: {exc}") from exc
        stamp = _file_stamp(path)
        if stamp is None:
            raise OSError(f"could not fingerprint verifier candidate {path}")
        ranked.append((asm_floor, path.name, path, stamp))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked


def _candidate_inventory_stamps(directory: Path) -> list[tuple[str, tuple[int, int, int, int, int]]]:
    """Recheck inventory membership and metadata without rereading source bodies."""
    verified_root = directory.resolve()
    current = []
    for path in directory.iterdir():
        if path.suffix.lower() not in SOURCE_LANGUAGES:
            continue
        if path.name.startswith(".agentdecompile-"):
            continue
        if path.is_symlink() or path.resolve().parent != verified_root:
            raise OSError(f"verifier candidate is not a regular child of verified-dir: {path}")
        stamp = _file_stamp(path)
        if stamp is None:
            raise OSError(f"could not fingerprint verifier candidate {path}")
        current.append((path.name, stamp))
    current.sort(key=lambda item: item[0])
    return current


def _cache_basis(raw: bytes, compiler: str, size_map: dict[int, int],
                 manifest_path: str | None,
                 environment: dict[str, str] | None = None) -> tuple[str, bool]:
    """Hash observed inputs; caller explicitly declares transitive closure completeness.

    A wrapper's bytes cannot identify every compiler, DLL, header or environment
    value it consumes. Without a complete manifest old positive claims are never
    reusable, although fresh compilation and bounded failure retry remain possible.
    """
    wrapper = Path(compiler).resolve()
    bash = shutil.which("bash")
    manifest: dict = {}
    closure: list[tuple[str, str]] = []
    if manifest_path:
        manifest_file = Path(manifest_path).resolve()
        manifest = json.loads(manifest_file.read_text())
        if not isinstance(manifest, dict) or manifest.get("complete") is not True:
            raise ValueError("cache input manifest must declare complete=true")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries or not all(isinstance(x, str) for x in entries):
            raise ValueError("cache input manifest requires a nonempty files list")
        for entry in entries:
            path = Path(entry)
            if not path.is_absolute():
                path = manifest_file.parent / path
            path = path.resolve()
            closure.append((str(path), _digest(path.read_bytes())))
    names = manifest.get("environment", [])
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise ValueError("cache input manifest environment must be a list of names")
    env_names = sorted(set(names) | {"PATH", "VCROOT", "CL", "_CL_", "CL_OPT",
                                    "WINEPREFIX", "WINELOADER", "WINESERVER",
                                    "WINEDEBUG", "WINEPATH", "INCLUDE", "LIB"})
    basis = {
        "raw": _digest(raw), "compiler": str(wrapper), "wrapper": _digest(wrapper.read_bytes()),
        "bash": (bash, _digest(Path(bash).read_bytes()) if bash else None),
        "pythonRuntime": {"executable": str(Path(sys.executable).resolve()),
                          "version": sys.version,
                          "sha256": _file_digest(Path(sys.executable))
                          if wrapper.suffix == ".py" else None},
        "verifier": _VERIFIER_REVISION, "preamble": _digest(_PREAMBLE.encode()),
        "preambleRecipe": _digest(Path(__file__).with_name("recovered_c_preamble.py").read_bytes()),
        "sizes": sorted(size_map.items()), "closure": sorted(closure),
        "environment": {name: (os.environ if environment is None else environment).get(name)
                        for name in env_names},
        "manifest": manifest,
    }
    return _digest(json.dumps(basis, sort_keys=True).encode()), bool(manifest)


def _cache_reusable(entry: dict, key: str, complete: bool, now: float) -> bool:
    if entry.get("key") != key or not isinstance(entry.get("result"), dict):
        return False
    if entry["result"].get("sourceAttempted") is False:
        return False
    if entry["result"].get("ok") not in (True, False):
        return False
    if entry["result"].get("reason") in _STABLE_REASONS:
        return complete and _artifacts_valid(entry)
    deadline = entry.get("retry_after")
    recorded = entry.get("observed_at")
    # A clock rollback must not turn an unknown failure into permanent cache.
    return (type(deadline) in (int, float) and type(recorded) in (int, float)
            and math.isfinite(deadline) and math.isfinite(recorded) and recorded <= now < deadline)


def _historical_output_roots(document: dict, entries: dict[str, dict]) -> list[str | None] | None:
    """Recover old key roots from explicit metadata or unambiguous artifact ownership."""
    roots = document.get("outputRoots")
    if (isinstance(roots, list) and len(roots) == 2
            and all(value is None or isinstance(value, str) for value in roots)):
        return roots
    observed: dict[str, set[str]] = {"raw-exact": set(), "max-c-diagnostic": set()}
    for entry in entries.values():
        artifacts = entry.get("artifacts", [])
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            channel = artifact.get("channel")
            path = artifact.get("path")
            if channel in observed and isinstance(path, str):
                observed[channel].add(str(Path(path).resolve().parent))
    if all(len(observed[channel]) == 1 for channel in observed):
        return [next(iter(observed["raw-exact"])),
                next(iter(observed["max-c-diagnostic"]))]
    return None


def _artifacts_valid(entry: dict) -> bool:
    artifacts = entry.get("artifacts", [])
    if not isinstance(artifacts, list):
        return False
    try:
        result = entry.get("result", {})
        address = _result_address(result)
        source_path = result.get("sourcePath")
        source_sha256 = result.get("sourceSha256")
        basis = entry.get("basis")
        for item in artifacts:
            if (not isinstance(item, dict) or address is None
                    or not isinstance(source_path, str) or not isinstance(source_sha256, str)
                    or not isinstance(basis, str)):
                return False
            path = Path(item["path"]).resolve()
            expected = {
                "sourcePath": source_path,
                "sourceSha256": source_sha256,
                "basis": basis,
                "address": address,
                "sha256": item["sha256"],
                "channel": item["channel"],
            }
            if (_digest(path.read_bytes()) != item["sha256"]
                    or _load_artifact_owners(path.parent).get(path.name) != expected):
                return False
        return True
    except (OSError, KeyError, TypeError):
        return False


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verified-dir", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--ghidra-filebytes-receipt",
                    help="fresh target-image receipt returned by the corpus CLI's Ghidra FileBytes resolver")
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--compiler-options", help="Opt-in per-job owned MSVC CL_OPT override")
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume-state",
                    help="override the prior-state source; otherwise use this output's state or discover the target's canonical state")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--offset", type=int, default=None,
                    help="zero-based position in the non-assembly-first candidate order")
    ap.add_argument("--candidate", action="append", default=[], metavar="NAME_OR_ADDRESS",
                    help="verify one exact C/C++ basename or unique hex address; repeatable")
    ap.add_argument("--db", help="corpus DB for function sizes (pools whose header omits size:)")
    ap.add_argument("--binary-id", type=int, help="binary_id for the --db size lookup")
    ap.add_argument("--bin-dir", help="also emit <addr>.bin substitution inputs for "
                    "relocation-free byte-exact functions (feeds whole_image_relink)")
    ap.add_argument("--maxc-bin-dir", help="emit slot-fitting compiled bytes for ANY compiling "
                    "function (byte-exact or not) for the readable max-C image")
    ap.add_argument("--no-incremental", action="store_true",
                    help="explicit fresh recompile of every selected function, ignoring cached outcomes")
    ap.add_argument("--cache-input-manifest", help="declared compiler/runtime closure; complete=true is required for verified cache reuse")
    ap.add_argument("--transient-retry-seconds", type=float, default=300.0,
                    help="minimum cooldown before retrying an inconclusive compiler result")
    args = ap.parse_args(argv)
    try:
        compiler_environment = _compiler_environment(args.compiler, args.compiler_options)
    except ValueError as error:
        ap.error(str(error))
    run_started = time.monotonic()
    if not math.isfinite(args.transient_retry_seconds) or args.transient_retry_seconds <= 0:
        ap.error("--transient-retry-seconds must be positive")
    from .verification_selection import validate_selection

    selection_errors = validate_selection(candidate=args.candidate, offset=args.offset, limit=args.limit)
    if selection_errors:
        ap.error("; ".join(selection_errors))
    if not Path(args.verified_dir).is_dir():
        ap.error(f"--verified-dir is not an existing directory: {args.verified_dir}")
    out_path = Path(args.out)
    scratch_root = Path(
        os.environ.get("AGENT_DECOMPILE_VERIFIER_TMPDIR")
        or out_path.parent / ".verify-scratch" / out_path.stem
    ).expanduser()
    scratch_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch_root)
    tempfile.tempdir = str(scratch_root)
    state_path = out_path.with_suffix(out_path.suffix + ".state.json")
    cache_input_path = Path(args.resume_state) if args.resume_state else state_path
    if not args.resume_state:
        if state_path.is_file():
            try:
                existing_state = json.loads(state_path.read_text())
            except (OSError, ValueError):
                existing_state = None
            if not isinstance(existing_state, dict) or existing_state.get("schema") != CACHE_SCHEMA:
                ap.error("refusing to overwrite an unrecognized or legacy verifier state; choose a new --out path")
        else:
            verified_root = Path(args.verified_dir).expanduser().resolve()
            canonical_state = verified_root.parent / f"{verified_root.name}.byteexact.json.state.json"
            if canonical_state.is_file() and canonical_state.resolve() != state_path.resolve():
                cache_input_path = canonical_state
                print(f"using prior verifier state as read-only history: {canonical_state}", flush=True)
    resume_state_active = cache_input_path.resolve() != state_path.resolve()
    if args.resume_state and cache_input_path.resolve() in {out_path.resolve(), state_path.resolve()}:
        ap.error("--resume-state must be separate from the new receipt and state output paths")

    bin_dir = None
    if args.bin_dir:
        bin_dir = Path(args.bin_dir)
        bin_dir.mkdir(parents=True, exist_ok=True)
    maxc_dir = None
    if getattr(args, "maxc_bin_dir", None):
        maxc_dir = Path(args.maxc_bin_dir)
        maxc_dir.mkdir(parents=True, exist_ok=True)
    artifact_roots = {str(root.resolve()): root for root in (bin_dir, maxc_dir) if root is not None}
    root_locks = []
    if artifact_roots:
        import fcntl
        for root_key in sorted(artifact_roots):
            root = artifact_roots[root_key]
            lock = (root / ".agentdecompile-artifact-owners.lock").open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                for held in root_locks:
                    held.close()
                raise ArtifactPublicationError([{
                    "path": str(root.resolve()),
                    "reason": "artifact_output_owner_active",
                }])
            root_locks.append(lock)

    # Put actual C candidates ahead of assembly-floor placeholders. Recent
    # K1 prefixes contained mostly these non-compiling stubs, starving the
    # first bounded verifier slices of useful compiler evidence.
    inventory_started = time.monotonic()
    verified_dir = Path(args.verified_dir)
    # Hex selectors are resolved by header identity and must remain unique
    # across the full pool. Exact basenames can be resolved without walking it.
    explicit_names_only = bool(args.candidate)
    if explicit_names_only:
        for selector in args.candidate:
            if not selector or Path(selector).name != selector or "/" in selector or "\\" in selector:
                ap.error(f"unsafe --candidate value (expected an exact C/C++ basename or hex address): {selector!r}")
            if Path(selector).suffix.lower() not in SOURCE_LANGUAGES:
                if _ADDRESS_SELECTOR_RE.fullmatch(selector):
                    explicit_names_only = False
                    break
                ap.error(f"unknown --candidate value: {selector!r}")
    if explicit_names_only:
        ranked_files = []
        for selector in args.candidate:
            candidate_path = verified_dir / selector
            if (selector.startswith(".agentdecompile-")
                    or (not candidate_path.exists() and not candidate_path.is_symlink())):
                ap.error(f"unknown --candidate value: {selector!r}")
            ranked_files.append(_candidate_entry(verified_dir, candidate_path))
    else:
        # Offset/limit/default ordering and address-selector uniqueness require
        # the complete source inventory. Basename-only selections above are
        # deliberately scoped to their named children.
        ranked_files = _candidate_inventory(verified_dir)
    if not ranked_files:
        ap.error(f"--verified-dir contains no recovered C/C++ candidates: {args.verified_dir}")
    inventory_seconds = time.monotonic() - inventory_started
    setup_seconds = inventory_started - run_started
    inventory_snapshot = sorted((item[1], item[3]) for item in ranked_files)
    inventory_stamps_by_name = dict(inventory_snapshot)
    inventory_files = [item[2] for item in ranked_files]
    files = inventory_files
    asm_floor_count = sum(item[0] for item in ranked_files)
    inventory_names = [item[1] for item in ranked_files]
    inventory_identity = [(item[1], list(item[3])) for item in ranked_files]
    inventory_digest = _digest(json.dumps(inventory_identity, separators=(",", ":")).encode())
    selected_offset = args.offset if args.offset is not None else 0
    resolved_candidates: list[dict] = []
    inventory_scanned = not explicit_names_only
    if args.candidate:
        files, resolved_candidates = _select_candidates(ap, args.candidate, ranked_files)
        print(f"explicit candidates: {len(files)} selected; "
              f"{sum(not item[0] for item in ranked_files)} non-assembly, "
              f"{asm_floor_count} assembly-floor", flush=True)
    else:
        print(f"candidate order: {len(files) - asm_floor_count} non-assembly sources first; "
              f"{asm_floor_count} assembly-floor sources deferred", flush=True)
        if args.offset:
            files = files[args.offset:]
        if args.limit is not None:
            files = files[:args.limit]
    artifact_owners = {key: _load_artifact_owners(root) for key, root in artifact_roots.items()}
    source_paths = {str(path.resolve()) for path in files}

    def withdraw_failed_run_outputs() -> list[str]:
        # A prior state source is historical user data. Even preflight failure
        # must not mutate its artifact-owner manifests or files.
        if resume_state_active:
            return []
        return _withdraw_manifest_sources(artifact_roots, artifact_owners, source_paths)

    try:
        raw = Path(args.raw).read_bytes()
        raw_stamp = _file_stamp(Path(args.raw))
    except OSError:
        withdraw_failed_run_outputs()
        raise
    target_snapshot = {'path': str(Path(args.raw).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'size': len(raw), 'scope': 'captured-image-snapshot',
                       'observation': 'invocation-pinned', 'currentFileVerified': False}
    if args.ghidra_filebytes_receipt:
        receipt_path = Path(args.ghidra_filebytes_receipt).resolve()
        try:
            receipt_bytes = receipt_path.read_bytes()
            receipt = json.loads(receipt_bytes)
            provenance = receipt.get('sourceProvenance') if isinstance(receipt, dict) else None
            raw_digest = target_snapshot['sha256']
            valid_receipt = (
                isinstance(receipt, dict)
                and receipt.get('schema') == 'agentdecompile.original-target.v1'
                and receipt.get('state') == 'ready'
                and receipt.get('authority') == 'original-imported-executable'
                and Path(str(receipt.get('targetPath') or '')).resolve() == Path(args.raw).resolve()
                and receipt.get('sourceSha256') == raw_digest
                and receipt.get('expectedSha256') == raw_digest
                and receipt.get('targetSha256') == raw_digest
                and receipt.get('programFingerprint') == raw_digest
                and isinstance(provenance, dict)
                and provenance.get('kind') == 'ghidra-file-bytes'
                and provenance.get('binding') == 'corpus-program-binding'
                and provenance.get('sha256') == raw_digest
                and provenance.get('size') == len(raw)
                and provenance.get('resolver') in {
                    'ghidra_store_file_bytes', 'ghidra_repository', 'ghidra_file_bytes'
                }
            )
            if valid_receipt:
                target_snapshot['ghidraFileBytesReceipt'] = {
                    'path': str(receipt_path),
                    'sha256': _digest(receipt_bytes),
                    'program': receipt.get('program'),
                    'resolver': provenance.get('resolver'),
                    'verifiedAt': receipt.get('verifiedAt'),
                    'authority': 'Ghidra program FileBytes; image and receipt hashes agree',
                }
        except (OSError, ValueError, TypeError):
            # A missing or malformed provenance receipt never upgrades the
            # invocation-pinned target claim.
            pass
    mapper = pe_mapper(raw)
    size_map: dict[int, int] = {}
    if args.db and args.binary_id is not None:
        try:
            con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
            size_map = {int(a): int(s or 0) for a, s in con.execute(
                "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
            con.close()
        except (OSError, sqlite3.Error):
            withdraw_failed_run_outputs()
            raise
        print(f"loaded {len(size_map)} function sizes from DB", flush=True)
    runtime_inputs = [Path(__file__).resolve(),
                      Path(__file__).with_name("recovered_c_preamble.py").resolve(),
                      Path(args.compiler).resolve(), Path(args.raw).resolve()]
    if args.db and args.binary_id is not None:
        runtime_inputs.append(Path(args.db).resolve())
    if Path(args.compiler).suffix == ".py":
        runtime_inputs.append(Path(sys.executable).resolve())
    bash_path = shutil.which("bash")
    if bash_path:
        runtime_inputs.append(Path(bash_path).resolve())
    if args.cache_input_manifest:
        manifest_file = Path(args.cache_input_manifest).resolve()
        runtime_inputs.append(manifest_file)
        manifest_data = json.loads(manifest_file.read_text())
        for entry in manifest_data.get("files", []):
            path = Path(entry)
            runtime_inputs.append((path if path.is_absolute() else manifest_file.parent / path).resolve())
    runtime_inputs = list(dict.fromkeys(runtime_inputs))
    # Capture stamps before basis hashing. If an input changes while the basis
    # is being calculated, publication detects the changed stamp and re-hashes
    # rather than trusting an observation made across a moving toolchain.
    runtime_stamps = {path: _file_stamp(path) for path in runtime_inputs}
    runtime_environment = dict(os.environ)
    try:
        basis, complete = _cache_basis(raw, args.compiler, size_map, args.cache_input_manifest,
                                      compiler_environment)
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: cache-basis-unavailable: {exc}", flush=True)
        withdrawn = withdraw_failed_run_outputs()
        _write_json_atomic(out_path, {"total": 0, "byteExact": 0, "results": [],
                                      "current": False, "reason": "cache-basis-unavailable",
                                      "withdrawnArtifacts": withdrawn})
        return 2
    target_snapshot['verificationBasis'] = {'sha256': basis, 'completeToolchainBasis': complete,
        'claim': 'Invocation observation; diagnostic retention does not establish compiler or whole-image acceptance.'}
    target_snapshot['compilerPolicy'] = {
        'override': args.compiler_options is not None,
        'CL_OPT': compiler_environment.get('CL_OPT'),
        'scope': 'Captured child environment; not a qualified original compiler profile.'}
    now = time.time()
    cache: dict[str, dict] = {}
    cache_document: dict = {}
    legacy_diagnostics: dict[str, dict] = {}
    historical_artifacts_preserved = 0
    if cache_input_path.is_file():
        try:
            document = json.loads(cache_input_path.read_text())
            if document.get("schema") == CACHE_SCHEMA:
                cache_document = document
                entries = document.get("entries", {})
                if isinstance(entries, dict):
                    cache = {k: v for k, v in entries.items() if isinstance(v, dict)}
                    if resume_state_active:
                        # A resume source is read-only history. Do not let a
                        # fresh receipt withdraw/quarantine artifacts owned by
                        # the old run; new output roots must earn new ownership.
                        historical_artifacts_preserved = sum(
                            len(entry.get("artifacts", []))
                            for entry in cache.values()
                            if isinstance(entry.get("artifacts", []), list)
                        )
                        cache = {name: dict(entry, artifacts=[])
                                 for name, entry in cache.items()}
            elif (resume_state_active and isinstance(document, dict)
                  and "schema" not in document and "entries" not in document):
                # Older verifier states were keyed by basename and stored only
                # an mtime:size signature plus a result. Preserve matching
                # selected rows as diagnostics, but never treat them as cache
                # entries: they do not bind source bytes or a toolchain basis.
                for source in files:
                    entry = document.get(source.name)
                    result = entry.get("result") if isinstance(entry, dict) else None
                    if (isinstance(result, dict) and result.get("file") == source.name
                            and isinstance(entry.get("sig"), str)):
                        legacy_diagnostics[source.name] = {
                            "result": result,
                            "signature": entry["sig"],
                        }
        except (OSError, ValueError, AttributeError):
            pass  # Old receipts are not upgraded to content-verified records.
    try:
        snapshots = {f.name: f.read_bytes() for f in files}
    except OSError:
        withdraw_failed_run_outputs()
        raise
    source_stamps = {f.name: _file_stamp(f) for f in files}
    output_roots = [str(p.resolve()) if p else None for p in (bin_dir, maxc_dir)]
    historical_entries = cache_document.get("entries", {})
    historical_roots = _historical_output_roots(
        cache_document, historical_entries if isinstance(historical_entries, dict) else {})
    keys = {name: _digest(json.dumps([basis, _digest(blob), output_roots]).encode())
            for name, blob in snapshots.items()}
    new_state: dict[str, dict] = dict(cache)
    results_by_name: dict[str, dict] = {}
    fresh: list[Path] = []
    historical_diagnostics: dict[str, dict] = {
        name: entry["result"] for name, entry in legacy_diagnostics.items()
    }
    reused_source_diagnostics = 0
    retained_comparisons: dict[str, dict] = {}
    halted: dict | None = None
    for f in files:
        entry = cache.get(f.name, {})
        prior_result = entry.get('result')
        reference = prior_result.get('diagnosticRetention') if isinstance(prior_result, dict) else None
        if not args.no_incremental and isinstance(reference, dict):
            retained_comparisons[f.name] = replay_retained_compiler_diagnostic(
                f, raw, mapper, args.compiler, reference, size_map,
                source_bytes=snapshots[f.name], target_snapshot=target_snapshot)
        if (not args.no_incremental and not complete and historical_roots is not None
                and entry.get("key") != keys[f.name]
                and isinstance(entry.get("basis"), str)
                and isinstance(entry.get("result"), dict)):
            # Historical outcomes are diagnostic-only. Reconstruct the old
            # key from the stored basis, current source bytes, and the old
            # output roots; never reuse its success/artifacts as current proof.
            historical_key = _digest(json.dumps([
                entry["basis"], _digest(snapshots[f.name]), historical_roots
            ]).encode())
            if entry.get("key") == historical_key:
                historical_diagnostics[f.name] = entry["result"]
        if not args.no_incremental and _cache_reusable(entry, keys[f.name], complete, now):
            new_state[f.name] = entry
            results_by_name[f.name] = dict(entry["result"], reused=True)
            signature = _failure_signature(entry["result"])
            if signature and halted is None:
                halted = {"reason": "first-failure",
                          "failureReason": entry["result"].get("reason"),
                          "diagnostic": signature,
                          "triggeringSource": f.name,
                          "reused": True}
                print(f"halting new compiler dispatch on previously recorded failure in {f.name}: "
                      f"{signature}", flush=True)
        elif (not args.no_incremental and not complete and entry.get("key") == keys[f.name]
              and entry.get("result", {}).get("reason") == "asm-floor"):
            # The assembly-floor marker is derived from the source text, not
            # compiler output. Reuse that classification for scheduling only;
            # it never counts as a compiled or byte-equivalent result.
            new_state[f.name] = entry
            results_by_name[f.name] = dict(entry["result"], reusedDiagnostic=True,
                                           diagnosticOnly=True, current=False)
            reused_source_diagnostics += 1
        else:
            if (not args.no_incremental and not complete and entry.get("key") == keys[f.name]
                    and isinstance(entry.get("result"), dict)):
                # Preserve the old finding alongside a fresh attempt. The
                # incomplete closure forbids accepting it as current proof,
                # but throwing it away would lose a useful failure signal.
                historical_diagnostics[f.name] = entry["result"]
            fresh.append(f)
    print(f"verifying {len(files)} recovered C/C++ files; {len(fresh)} new/changed or retry-eligible; "
          f"{len(files)-len(fresh)} reused/deferred", flush=True)

    def checkpoint() -> None:
        _write_json_atomic(state_path, {"schema": CACHE_SCHEMA,
                                        "outputRoots": output_roots,
                                        "entries": new_state})

    # Workers use frozen source text and private emitted bytes. Publication waits
    # for the complete basis and each source to be rechecked after compilation.
    verification_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="verify-pass-") as workspace:
        staging = Path(workspace)
        def run_group(group: list[Path]) -> dict[str, tuple[dict, list]]:
            staged_roots = {}
            distribution_info = {}
            for f in group:
                own = staging / f.name
                own.mkdir()
                staged_bin, staged_maxc = own / "bin", own / "maxc"
                staged_bin.mkdir()
                staged_maxc.mkdir()
                staged_roots[f.name] = (staged_bin, staged_maxc)
                distribution = None
                address = None
                distribution_started = time.monotonic()
                try:
                    from . import cross_place, cross_place_admission as admission
                    address = cross_place.parse_addr(snapshots[f.name].decode('utf-8'))
                    with admission.read_database(args.db) as distribution_db:
                        distribution = admission.capture_source_basis(
                            distribution_db, args.binary_id, address, f,
                            snapshots[f.name], target=args.raw)
                except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                    pass  # Distribution is narrower; local verification remains authoritative.
                distribution_info[f.name] = (distribution, address if distribution else None,
                                              time.monotonic() - distribution_started)

            results = verify_batch(
                group, raw, mapper, args.compiler, size_map,
                [staged_roots[f.name][0] if bin_dir else None for f in group],
                [staged_roots[f.name][1] if maxc_dir else None for f in group],
                snapshots, target_snapshot, compiler_environment)
            completed = {}
            for f, result in zip(group, results, strict=True):
                distribution, address, distribution_seconds = distribution_info[f.name]
                result["distributionObservationSeconds"] = round(distribution_seconds, 3)
                if distribution and result.get("ok"):
                    try:
                        with admission.read_database(args.db) as distribution_db:
                            current = admission.capture_source_basis(
                                distribution_db, args.binary_id, address, f,
                                snapshots[f.name], target=args.raw)
                        if current == distribution:
                            result["distribution"] = distribution
                    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                        pass  # Never downgrade a local result for unsupported distribution.
                emitted = []
                staged_bin, staged_maxc = staged_roots[f.name]
                for origin, destination, channel in (
                        (staged_bin, bin_dir, "raw-exact"),
                        (staged_maxc, maxc_dir, "max-c-diagnostic")):
                    if destination:
                        emitted.extend((p, destination / p.name, channel)
                                       for p in origin.glob("*.bin"))
                completed[f.name] = (result, emitted)
            return completed

        def withdraw_owned(entry: dict, f: Path) -> list[str]:
            """Atomically move only artifacts whose full ownership still matches."""
            withdrawn = []
            blocked = []
            result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
            address = _result_address(result)
            owner_source = str(f.resolve())
            owner_source_sha256 = result.get("sourceSha256")
            owner_basis = entry.get("basis")
            if (address is None or not isinstance(owner_basis, str)
                    or result.get("sourcePath") != owner_source
                    or not isinstance(owner_source_sha256, str)):
                if entry.get("artifacts"):
                    raise ArtifactPublicationError([{
                        "sourcePath": owner_source,
                        "reason": "artifact_entry_ownership_incomplete",
                    }])
                return withdrawn
            for artifact in entry.get("artifacts", []):
                if not isinstance(artifact, dict):
                    blocked.append({"sourcePath": owner_source, "address": address,
                                    "reason": "invalid_artifact_record"})
                    continue
                try:
                    path = Path(artifact["path"]).resolve()
                    root = path.parent
                    root_key = str(root)
                    channel = artifact["channel"]
                    expected = {
                        "sourcePath": owner_source,
                        "sourceSha256": owner_source_sha256,
                        "basis": owner_basis,
                        "address": address,
                        "sha256": artifact["sha256"],
                        "channel": channel,
                    }
                except (KeyError, OSError, TypeError):
                    blocked.append({"sourcePath": owner_source, "reason": "invalid_artifact_record"})
                    continue
                if root_key not in artifact_roots or path.name != f"{address:08x}.bin":
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_path_not_owned"})
                    continue
                recorded_owner = artifact_owners[root_key].get(path.name)
                if recorded_owner != expected:
                    # A prior fail-closed invocation may have durably withdrawn
                    # the file and owner before it could rewrite disposable
                    # cache state. That fully absent pair is already withdrawn;
                    # every present or conflicting case remains blocking.
                    if recorded_owner is None and not path.exists():
                        continue
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_owner_mismatch"})
                    continue
                try:
                    if path.is_file():
                        if _digest(path.read_bytes()) != expected["sha256"]:
                            blocked.append({"path": str(path), "sourcePath": owner_source,
                                            "address": address, "reason": "artifact_digest_mismatch"})
                            continue
                        quarantine = root / ".withdrawn"
                        quarantine.mkdir(exist_ok=True)
                        destination = quarantine / (
                            f"{path.name}.{owner_basis[:12]}.{expected['sha256'][:12]}.{time.time_ns()}"
                        )
                        os.replace(path, destination)
                        withdrawn.append(str(destination.resolve()))
                    artifact_owners[root_key].pop(path.name, None)
                    _write_artifact_owners(root, artifact_owners[root_key])
                except OSError as exc:
                    blocked.append({"path": str(path), "sourcePath": owner_source,
                                    "address": address, "reason": "artifact_quarantine_failed",
                                    "error": exc.__class__.__name__})
                    continue
            if blocked:
                raise ArtifactPublicationError(blocked)
            return withdrawn

        def withdraw_current_source(entry: dict, f: Path) -> list[str]:
            if resume_state_active:
                return []
            withdrawn = withdraw_owned(entry, f)
            withdrawn.extend(_withdraw_manifest_sources(
                artifact_roots, artifact_owners, {str(f.resolve())}
            ))
            return withdrawn

        def guard_active_paths(f: Path, address: int | None) -> None:
            """Refuse unowned/conflicting active paths left after withdrawal."""
            if address is None:
                return
            diagnostics = []
            for root_key, root in artifact_roots.items():
                path = root / f"{address:08x}.bin"
                if not path.is_file():
                    continue
                owner = artifact_owners[root_key].get(path.name)
                reason = None
                if not isinstance(owner, dict):
                    reason = "unowned_active_artifact"
                else:
                    try:
                        owner_valid = (owner.get("address") == address
                                       and isinstance(owner.get("sourcePath"), str)
                                       and isinstance(owner.get("sourceSha256"), str)
                                       and isinstance(owner.get("basis"), str)
                                       and isinstance(owner.get("channel"), str)
                                       and _digest(path.read_bytes()) == owner.get("sha256"))
                    except OSError:
                        owner_valid = False
                    if not owner_valid:
                        reason = "active_artifact_owner_invalid"
                    elif owner["sourcePath"] == str(f.resolve()):
                        reason = "owned_artifact_without_current_state"
                if reason:
                    diagnostics.append({"path": str(path.resolve()), "sourcePath": str(f.resolve()),
                                        "address": address, "reason": reason,
                                        "existingOwner": owner})
            if diagnostics:
                raise ArtifactPublicationError(diagnostics)

        def publish(pending: dict, *, final: bool = False) -> None:
            nonlocal halted
            changed_basis_inputs = (
                os.environ != runtime_environment
                or any(_file_stamp(path) != stamp for path, stamp in runtime_stamps.items())
            )
            current_basis = basis
            if changed_basis_inputs:
                try:
                    current_raw = Path(args.raw).read_bytes()
                    current_sizes = size_map
                    if args.db and args.binary_id is not None:
                        with sqlite3.connect(f"file:{args.db}?mode=ro", uri=True) as con:
                            current_sizes = {int(a): int(s or 0) for a, s in con.execute(
                                "SELECT addr, size FROM func WHERE binary_id=?", (args.binary_id,))}
                    current_basis, _ = _cache_basis(
                        current_raw, args.compiler, current_sizes, args.cache_input_manifest,
                        _compiler_environment(args.compiler, args.compiler_options))
                except (OSError, ValueError, TypeError, sqlite3.Error):
                    current_basis = None
            for f in (files if final else [p for p in fresh if p.name in pending]):
                try:
                    source_current = f.read_bytes() == snapshots[f.name]
                except OSError:
                    source_current = False
                if current_basis != basis or not source_current:
                    previous_entry = new_state.get(f.name, {})
                    withdrawn = withdraw_current_source(previous_entry, f)
                    previous_result = (previous_entry.get("result")
                                       if isinstance(previous_entry.get("result"), dict) else {})
                    pending_result = pending.get(f.name, ({}, []))[0]
                    guard_active_paths(f, _result_address(previous_result) or _result_address(pending_result))
                    results_by_name[f.name] = {"file": f.name, "ok": False,
                                               "reason": "inputs-changed-during-verification",
                                               "withdrawnArtifacts": withdrawn}
                    new_state.pop(f.name, None)
                    if halted is None:
                        halted = {"reason": "first-failure",
                                  "failureReason": "inputs-changed-during-verification",
                                  "triggeringSource": f.name}
                        print(f"halting new compiler dispatch because verification inputs changed: {f.name}",
                              flush=True)
                    continue
                if f.name not in pending:
                    continue
                result, emitted = pending[f.name]
                withdrawn = withdraw_current_source(new_state.get(f.name, {}), f)
                artifacts = []
                address = _result_address(result)
                guard_active_paths(f, address)
                for source, dest, channel in emitted:
                    if address is None or dest.name != f"{address:08x}.bin":
                        continue
                    if dest.exists():
                        raise ArtifactPublicationError([{
                            "path": str(dest.resolve()), "sourcePath": str(f.resolve()),
                            "address": address, "reason": "active_artifact_path_already_exists",
                            "existingOwner": artifact_owners[str(dest.parent.resolve())].get(dest.name),
                        }])
                    data = source.read_bytes()
                    descriptor, temporary_name = tempfile.mkstemp(
                        prefix=f".{dest.name}.", suffix=".tmp", dir=dest.parent
                    )
                    temporary = Path(temporary_name)
                    try:
                        with os.fdopen(descriptor, "wb") as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        try:
                            os.link(temporary, dest)
                        except FileExistsError:
                            raise ArtifactPublicationError([{
                                "path": str(dest.resolve()), "sourcePath": str(f.resolve()),
                                "address": address, "reason": "active_artifact_publish_race",
                                "existingOwner": artifact_owners[str(dest.parent.resolve())].get(dest.name),
                            }])
                    finally:
                        temporary.unlink(missing_ok=True)
                    artifact = {"path": str(dest.resolve()), "sha256": _digest(data),
                                "channel": channel, "address": address,
                                "ownerSourcePath": str(f.resolve()),
                                "ownerSourceSha256": _digest(snapshots[f.name]),
                                "ownerBasis": basis}
                    artifacts.append(artifact)
                    artifact_owners[str(dest.parent.resolve())][dest.name] = {
                        "sourcePath": str(f.resolve()),
                        "sourceSha256": _digest(snapshots[f.name]),
                        "basis": basis, "address": address,
                        "sha256": artifact["sha256"], "channel": channel,
                    }
                    _write_artifact_owners(dest.parent, artifact_owners[str(dest.parent.resolve())])
                if withdrawn:
                    result = dict(result, withdrawnArtifacts=withdrawn)
                observed = time.time()
                entry = {"key": keys[f.name], "result": result, "observed_at": observed,
                         "artifacts": artifacts, "basis": basis,
                         "complete_toolchain_basis": complete}
                if (result.get("reason") not in _STABLE_REASONS
                        and result.get("sourceAttempted") is not False):
                    # Rate limit only: a total per-function/incident spending cap
                    # belongs to the admission ledger, not this cache TTL.
                    entry["retry_after"] = observed + args.transient_retry_seconds
                new_state[f.name] = entry
                results_by_name[f.name] = dict(result, reused=False)
            for root_key, root in artifact_roots.items():
                _write_artifact_owners(root, artifact_owners[root_key])
            checkpoint()
        pending: dict[str, tuple[dict, list]] = {}
        next_fresh = 0
        in_flight = {}
        last_checkpoint = time.monotonic()
        batch_capable = _compiler_batch_capable(args.compiler)
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            while next_fresh < len(fresh) or in_flight:
                # A shared compiler failure must not overlap another group.
                # Adapter batching is deliberately serial at the
                # invocation level. Other compilers retain worker parallelism.
                max_groups = _verification_group_limit(batch_capable, args.workers)
                while (halted is None and next_fresh < len(fresh)
                       and len(in_flight) < max_groups):
                    group_size = _verification_group_size(batch_capable)
                    group = fresh[next_fresh:next_fresh + group_size]
                    in_flight[ex.submit(run_group, group)] = group
                    next_fresh += len(group)
                if not in_flight:
                    break
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    group = in_flight.pop(future)
                    try:
                        group_results = future.result()
                    except Exception as exc:  # Inconclusive execution is not a permanent negative.
                        group_results = {
                            source.name: ({"file": source.name, "ok": False,
                                           "reason": f"error:{exc.__class__.__name__}",
                                           "detail": str(exc)[:1000]}, [])
                            for source in group
                        }
                    for source in group:
                        item = group_results[source.name]
                        prior = historical_diagnostics.get(source.name)
                        if prior is not None:
                            item[0]["priorDiagnostic"] = {
                                key: prior[key] for key in (
                                    "reason", "failureClass", "compilerReturnCode",
                                    "compilerDiagnostic", "detail", "diff", "rawEqual",
                                    "maskedEqual") if key in prior
                            }
                            if source.name in legacy_diagnostics:
                                item[0]["priorDiagnostic"].update({
                                    "provenance": "legacy-mtime-size-only",
                                    "sourceContentBound": False,
                                    "toolchainBasisBound": False,
                                    "legacySignature": legacy_diagnostics[source.name]["signature"],
                                })
                        try:
                            current_source = source.read_bytes() == snapshots[source.name]
                            target_unchanged = _file_stamp(Path(args.raw)) == raw_stamp
                        except OSError:
                            current_source = target_unchanged = False
                        if not current_source or not target_unchanged:
                            item = ({"file": source.name, "ok": False,
                                     "reason": "inputs-changed-during-verification"}, [])
                        changed_runtime = [str(path) for path, stamp in runtime_stamps.items()
                                           if _file_stamp(path) != stamp]
                        if changed_runtime:
                            item = ({"file": source.name, "ok": False,
                                     "reason": "runtime-input-changed-during-verification",
                                     "detail": ", ".join(changed_runtime)}, [])
                        pending[source.name] = item
                        changed_pending = [name for name in pending
                                           if _file_stamp(Path(args.verified_dir) / name) != source_stamps[name]]
                        for name in changed_pending:
                            pending[name] = ({"file": name, "ok": False,
                                              "reason": "inputs-changed-during-verification"}, [])
                        if changed_pending and halted is None:
                            halted = {"reason": "first-failure",
                                      "failureReason": "inputs-changed-during-verification",
                                      "triggeringSource": changed_pending[0]}
                            print(f"halting new compiler dispatch because a pending source changed: "
                                  f"{changed_pending[0]}", flush=True)
                        signature = _failure_signature(item[0])
                        if signature and halted is None:
                            halted = {"reason": "first-failure",
                                      "failureReason": item[0].get("reason"),
                                      "diagnostic": signature,
                                      "triggeringSource": source.name}
                            print(f"halting new compiler dispatch after first failure in {source.name}: "
                                  f"{signature}; bounded in-flight work will be retained", flush=True)
                # Preserve completed compiler work on a time bound as well as
                # a count bound. With slow MSVC/Wine calls, waiting for 50
                # candidates could otherwise discard hours of successful
                # comparisons if the process or host stops mid-pass.
                if (len(pending) >= 50 or halted is not None
                        or time.monotonic() - last_checkpoint >= 30):
                    publish(pending)
                    pending.clear()
                    last_checkpoint = time.monotonic()
        publish(pending, final=True)
    if halted is not None:
        for source in fresh:
            if source.name not in results_by_name:
                results_by_name[source.name] = {
                    "file": source.name, "ok": False,
                    "reason": "not-run-after-first-failure",
                    "sourceAttempted": False,
                    "haltedBy": halted["reason"],
                }
    results = [results_by_name[f.name] for f in files]
    for result in results:
        if result['file'] in retained_comparisons:
            # This nested observation cannot change ok, cache disposition,
            # publication channels or fresh-compilation acceptance.
            result['retainedObjectComparison'] = retained_comparisons[result['file']]
        entry = new_state.get(result["file"], {})
        result["basis"] = basis
        result["sourceDigest"] = _digest(snapshots[result["file"]])
        result["sourceSha256"] = result["sourceDigest"]
        result["sourcePath"] = str((Path(args.verified_dir) / result["file"]).resolve())
        result["sourceLanguage"] = source_language(Path(result['file']))
        result["targetSnapshot"] = dict(target_snapshot)
        result["artifacts"] = entry.get("artifacts", []) if result.get("reason") not in {
            "cache-basis-incomplete", "inputs-changed-during-verification"} else []
        result["artifactsCurrent"] = bool(result["artifacts"]) and result.get("reason") in _STABLE_REASONS
    ok = [r for r in results if r.get("ok")]
    from .cross_place_checkpoint import publish_receipt
    selected_sources_stable = all(
        _file_stamp(Path(args.verified_dir) / name) == stamp
        for name, stamp in source_stamps.items()
    )
    try:
        if inventory_scanned:
            current_inventory = _candidate_inventory_stamps(verified_dir)
            inventory_stable: bool | None = current_inventory == inventory_snapshot
            selected_inventory_stable = inventory_stable
        else:
            selected_inventory_stable = (
                _selected_candidate_stamps(verified_dir, files) == inventory_snapshot
            )
            # None means the surrounding pool was intentionally not scanned;
            # selected-source stability is recorded independently below.
            inventory_stable = None
    except OSError:
        inventory_stable = False if inventory_scanned else None
        selected_inventory_stable = False
    slice_complete = (halted is None and selected_inventory_stable and selected_sources_stable
                      and (not inventory_scanned or inventory_stable)
                      and not any(r.get("reason") in {
                          "cache-basis-incomplete", "inputs-changed-during-verification"}
                          for r in results))
    selected_inventory_identity = [(path.name, list(inventory_stamps_by_name[path.name])
                                    if path.name in inventory_stamps_by_name else None)
                                   for path in files]
    selected_identifiers = (resolved_candidates if args.candidate else [
        {"identifier": path.name, "kind": "inventory", "file": path.name}
        for path in files
    ])
    full_inventory_covered = bool(
        inventory_scanned and selected_inventory_identity == inventory_identity and inventory_stable
    )
    coverage = {"inventoryScope": "verified-dir" if inventory_scanned else "selected-candidates",
                "inventoryCount": len(inventory_names),
                "inventorySha256": inventory_digest,
                "selectedOffset": selected_offset,
                "selectedCount": len(files),
                "selectionMode": "explicit-candidates" if args.candidate else "inventory-slice",
                "selectedIdentifiers": selected_identifiers,
                "selectedInventorySha256": _digest(json.dumps(
                    selected_inventory_identity, separators=(",", ":")).encode()),
                "inventoryStableAtEnd": inventory_stable,
                "selectedInventoryStableAtEnd": selected_inventory_stable,
                "selectedSourcesStableAtEnd": selected_sources_stable,
                "fullInventoryCovered": full_inventory_covered}
    # `complete` is a corpus-level claim consumed by downstream automation.
    # A successful --offset/--limit pilot is only a complete slice, never a
    # complete verifier pass over the corpus.
    coverage_complete = slice_complete and full_inventory_covered and complete
    verification_seconds = time.monotonic() - verification_started
    total_seconds = time.monotonic() - run_started
    publish_receipt(out_path.parent, out_path, {"total": len(results), "byteExact": len(ok), "results": results,
                                  "basis": basis, "completeToolchainBasis": complete,
                                  "complete": coverage_complete,
                                  "sliceComplete": slice_complete,
                                  "timings": {"setupSeconds": round(setup_seconds, 3),
                                              "inventorySeconds": round(inventory_seconds, 3),
                                              "verificationSeconds": round(verification_seconds, 3),
                                              "totalSeconds": round(total_seconds, 3)},
                                  "coverage": coverage, "halted": halted,
                                  "reuse": {"cacheInput": str(cache_input_path.resolve()),
                                            "cacheEntriesLoaded": len(cache),
                                            "historicalArtifactsLeftUntouched": historical_artifacts_preserved,
                                            "legacyDiagnosticsLoaded": len(legacy_diagnostics),
                                            "sourceOnlyDiagnosticsReused": reused_source_diagnostics,
                                            "freshAttemptsWithPriorDiagnostic": len(historical_diagnostics)},
                                  "scope": "local-relocation-masked; not whole-image or fresh-source acceptance"})
    from collections import Counter
    print(f"\nCurrent byte-exact (relocation-masked, reused entries labeled): {len(ok)}/{len(results)} "
          f"({100*len(ok)/max(len(results),1):.1f}%)")
    print("reasons:", dict(Counter(r.get("reason", "?") for r in results)))
    print("receipts:", args.out)
    return 2 if halted is not None or any(r.get("reason") in {
        "cache-basis-incomplete", "inputs-changed-during-verification"} for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Serialize cache and output publication even when called outside the periodic wrapper.
    output = next((value.split("=", 1)[1] for value in arguments if value.startswith("--out=")), None)
    if "--out" in arguments:
        index = arguments.index("--out")
        if index + 1 < len(arguments):
            output = arguments[index + 1]
    if output is None:
        return _main(arguments)  # argparse supplies the normal usage error/help.
    try:
        import fcntl
    except ImportError:
        print("error: verification requires POSIX flock support on this host", flush=True)
        return 2
    try:
        with Path(str(Path(output).resolve()) + ".verify.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("error: verification-output-owner-active", flush=True)
                return 2
            try:
                return _main(arguments)
            except ArtifactPublicationError as exc:
                print("error: artifact-publication-blocked", flush=True)
                _write_json_atomic(Path(output), {
                    "total": 0,
                    "byteExact": 0,
                    "results": [],
                    "current": False,
                    "reason": "artifact-publication-blocked",
                    "unresolvedArtifacts": exc.diagnostics,
                })
                return 2
            except (OSError, sqlite3.Error) as exc:
                print(f"error: verification-input-or-output-unavailable: {exc}", flush=True)
                # Invalidate only while holding publication authority. An open or
                # acquisition failure must never overwrite another owner's receipt.
                try:
                    _write_json_atomic(Path(output), {"total": 0, "byteExact": 0, "results": [],
                                                     "current": False, "reason": "verification-input-or-output-unavailable"})
                except OSError:
                    pass
                return 2
    except OSError as exc:
        print(f"error: verification-output-lock-unavailable: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
