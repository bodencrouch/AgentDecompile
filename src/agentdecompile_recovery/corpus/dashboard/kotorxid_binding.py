"""Read-only adapter for KotorXID's K1 GOG candidate/provenance rows.

This module deliberately does not use the AgentDecompile corpus store API.
KotorXID rows are proposals only; the selected AgentDecompile artifact and its
strict verifier remain authoritative for target identity and byte-level proof.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


K1_GOG_REPO_PATH = "/K1/k1_win_gog_swkotor.exe"
KX_CANDIDATE_SCHEMA_FINGERPRINT = "fee5c66740e383e1853bb19506d188f44242385477ba2c264c9893c5682cdfe3"

_REQUIRED_COLUMNS = {
    "binary": {"id", "repo_path", "slug", "md5"},
    "func": {"binary_id", "addr", "name", "size", "canon_key", "calling_convention"},
    "reuse_candidate": {
        "src_program", "src_name", "dst_binary_id", "dst_addr", "dst_name",
        "size", "real_c", "basis",
    },
    "recovered_function": {"program", "name", "path", "evidence", "real_c"},
}


class KotorXIDSourceError(ValueError):
    """The explicit KotorXID source cannot safely supply candidate proposals."""


class _CandidateSourceReadError(Exception):
    def __init__(self, reason_code: str, detail: str):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class CandidateExclusion:
    """Candidate omitted because its source cannot be safely frozen."""

    target_address: int
    source_program: str
    source_name: str
    recorded_source_path: str
    reason_code: str
    detail: str = ""


@dataclass(frozen=True)
class PreservedSelectionSnapshot:
    """Explicit historical materialization input, never verification authority."""

    manifest_path: str
    manifest_sha256: str
    manifest_stat: tuple[int, int, int, int, int]
    materialized_binaries_root: str


@dataclass(frozen=True)
class CandidateProposal:
    """One non-authoritative candidate with row-level source provenance."""

    target_address: int
    target_name: str | None
    function_name: str | None
    target_size: int | None
    reuse_size: int | None
    target_canonical_key: str | None
    target_calling_convention: str | None
    source_program: str
    source_name: str
    source_path: str
    recorded_source_path: str
    source_file_sha256: str
    source_file_identity: str
    source_file_stat: tuple[int, int, int, int, int]
    source_evidence: str | None
    source_real_c: bool
    reuse_real_c: bool
    basis: str
    work_item_key: str
    source_kind: str = "recorded_source"
    preserved_selection: PreservedSelectionSnapshot | None = None
    preserved_row_json: str | None = None
    preserved_donor_json: str | None = None
    declared_source_sha256: str | None = None
    reason_codes: tuple[str, ...] = ()
    trust: str = "untrusted_candidate"
    provenance: tuple[str, ...] = (
        "reuse_candidate", "recovered_function", "func", "binary",
    )


@dataclass(frozen=True)
class KotorXIDCandidateSource:
    """Frozen transaction rows and candidates for one selected artifact.

    DB sizes/versions/sidecars and file_identity are diagnostic provenance;
    file_identity is not a raw SQLite snapshot hash or current-version claim.
    """

    database_path: str
    database_size: int
    allowed_source_root: str
    file_identity: str
    schema_fingerprint: str
    observed_user_version: int
    observed_data_version: int
    sqlite_sidecar_identity: tuple[Any, ...]
    observed_migration_tables: tuple[str, ...]
    target_repo_path: str
    target_binary_id: int
    target_slug: str
    selected_target_sha256: str
    selected_target_md5: str
    candidates: tuple[CandidateProposal, ...]
    exclusions: tuple[CandidateExclusion, ...]
    preserved_selection: PreservedSelectionSnapshot | None = None
    preserved_manifest_bytes_hex: str | None = None
    preserved_donor_binaries_json: str | None = None
    source_kind: str = "kotorxid_candidate_proposals"
    authority: str = "proposal_only_not_verification"


def _one_file_identity(
    path: Path, *, optional: bool = False, nonempty: bool = True
) -> tuple[int, int, int, int, int] | None:
    try:
        info = path.stat()
    except OSError as exc:
        if optional and exc.errno == errno.ENOENT:
            return None
        raise KotorXIDSourceError(f"Cannot stat explicit KotorXID database: {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or (nonempty and info.st_size <= 0):
        raise KotorXIDSourceError(
            f"KotorXID database must be nonempty and any SQLite sidecars regular files: {path}"
        )
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stat_identity(path: Path) -> tuple[Any, ...]:
    main = _one_file_identity(path)
    assert main is not None
    return (
        main,
        _one_file_identity(Path(f"{path}-wal"), optional=True, nonempty=False),
        _one_file_identity(Path(f"{path}-shm"), optional=True, nonempty=False),
    )


def _resolve_source_file(root: Path, recorded_path: str) -> tuple[Path | None, str, str]:
    if not recorded_path.strip() or "\x00" in recorded_path:
        return None, "source_path_invalid", "recovered_function.path is blank or contains NUL."
    try:
        candidate = Path(recorded_path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        lexical_path = Path(os.path.abspath(candidate))
        try:
            lexical_path.relative_to(root)
        except ValueError:
            return None, "source_file_outside_selected_root", "Recorded source path escapes the explicitly selected root."
        canonical = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        # Resolve the missing tail non-strictly too: an escaping symlink must
        # never become permission to use historical materialization instead.
        try:
            candidate.resolve(strict=False).relative_to(root)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None, "source_file_outside_selected_root", "Missing path cannot be contained safely."
        return None, "source_file_missing", str(exc)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, "source_file_unavailable", str(exc)
    try:
        canonical.relative_to(root)
    except ValueError:
        return None, "source_file_outside_selected_root", "Resolved source path escapes the explicitly selected root."
    try:
        info = canonical.stat()
    except OSError as exc:
        return None, "source_file_unavailable", str(exc)
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
        return None, "source_file_not_nonempty_regular_file", "Resolved source is not a nonempty regular file."
    return canonical, "", ""


def _hash_source_file(path: Path) -> tuple[str, str, int, tuple[int, int, int, int, int]]:
    try:
        before = _one_file_identity(path)
        assert before is not None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = _one_file_identity(path)
    except (OSError, KotorXIDSourceError) as exc:
        raise _CandidateSourceReadError("source_file_unreadable", str(exc)) from exc
    if before != after:
        raise _CandidateSourceReadError(
            "source_file_changed_during_hash", "Source file changed while its SHA-256 was computed."
        )
    identity = hashlib.sha256(json.dumps((str(path), before), separators=(",", ":")).encode()).hexdigest()
    return digest.hexdigest(), identity, before[2], before


def read_frozen_candidate_bytes(
    proposal: CandidateProposal,
    *,
    allowed_source_root: str | Path,
) -> bytes:
    """Return the proposal-frozen bytes; compilers must not reopen its path."""
    try:
        root = Path(allowed_source_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise OSError("not a directory")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise KotorXIDSourceError(f"Explicit allowed source root is unavailable: {exc}") from exc
    if proposal.source_kind == "preserved_selection":
        selection = proposal.preserved_selection
        if selection is None:
            raise KotorXIDSourceError("Preserved candidate has no frozen manifest binding.")
        try:
            # Recheck the complete file identity/hash, but do not parse or copy
            # the entire manifest into every candidate's receipt.
            manifest_hash = _hash_source_file(Path(selection.manifest_path))
            if manifest_hash[0] != selection.manifest_sha256 or manifest_hash[3] != selection.manifest_stat:
                raise KotorXIDSourceError("Preserved selection bytes or identity changed.")
            donor = json.loads(proposal.preserved_donor_json or "null")
            selected = json.loads(proposal.preserved_row_json or "null")
            if not isinstance(donor, dict) or not isinstance(selected, dict):
                raise KotorXIDSourceError("Preserved candidate lacks frozen donor/row provenance.")
            compact_manifest = {
                "schema_version": 1, "binaries": [donor],
                "verified_c": {donor["slug"]: [selected]},
            }
            resolved, selected_row = _resolve_preserved_source(
                root, selection, compact_manifest, [donor], proposal.source_program,
                proposal.source_name, proposal.recorded_source_path,
            )
            if selected_row != proposal.preserved_row_json:
                raise KotorXIDSourceError("Preserved candidate row binding changed.")
            if json.loads(selected_row)["sha256"] != proposal.declared_source_sha256:
                raise KotorXIDSourceError("Preserved candidate declared hash binding changed.")
            if proposal.declared_source_sha256 != proposal.source_file_sha256:
                raise KotorXIDSourceError("Preserved candidate observed hash disagrees with manifest.")
        except _CandidateSourceReadError as exc:
            raise KotorXIDSourceError(f"{exc.reason_code}: {exc.detail}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise KotorXIDSourceError(f"Preserved candidate binding is invalid: {exc}") from exc
        reason, detail = "", ""
    elif proposal.source_kind == "recorded_source":
        resolved, reason, detail = _resolve_source_file(root, proposal.recorded_source_path)
    else:
        raise KotorXIDSourceError("Unknown frozen candidate source kind.")
    if resolved is None or str(resolved) != proposal.source_path:
        raise KotorXIDSourceError(
            f"Frozen candidate path no longer resolves within its allowed root ({reason or 'path_changed'}): {detail}"
        )
    return _read_pinned_bytes(resolved, proposal.source_file_stat, proposal.source_file_sha256)


def _read_pinned_bytes(
    resolved: Path, expected_stat: tuple[int, int, int, int, int], expected_sha256: str,
) -> bytes:
    """Read a pinned regular file through one checked descriptor."""
    try:
        if _one_file_identity(resolved) != expected_stat:
            raise KotorXIDSourceError("Frozen candidate source file identity changed; discard this work item.")
        descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            opened_stat = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            if opened_stat != expected_stat:
                raise KotorXIDSourceError("Opened candidate differs from its frozen source identity.")
            chunks: list[bytes] = []
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    chunks.append(chunk)
                    digest.update(chunk)
            after = os.fstat(descriptor)
            after_stat = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            if opened_stat != after_stat:
                raise KotorXIDSourceError("Candidate source changed while frozen bytes were read.")
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
    except KotorXIDSourceError:
        raise
    except OSError as exc:
        raise KotorXIDSourceError(f"Cannot read frozen candidate source bytes: {exc}") from exc
    if digest.hexdigest() != expected_sha256:
        raise KotorXIDSourceError("Candidate bytes do not match the proposal's frozen SHA-256.")
    return content


def _resolve_preserved_source(
    root: Path, selection: PreservedSelectionSnapshot, manifest: dict[str, Any],
    donor_rows: list[dict[str, Any]],
    source_program: str, source_name: str, recorded_path: str,
) -> tuple[Path, str]:
    def reject(code: str, detail: str) -> None:
        raise _CandidateSourceReadError(code, detail)

    donors = [row for row in donor_rows
              if source_program in (row["repo_path"], Path(row["repo_path"]).name)]
    if len(donors) != 1:
        reject("preserved_donor_binding_missing" if not donors else "preserved_donor_binding_ambiguous",
               "Source program must identify exactly one consumed binary row.")
    donor = donors[0]
    slug = donor["slug"]
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9_+.-]+", slug) or slug in (".", ".."):
        reject("preserved_path_invalid", "Donor slug is not a safe path component.")
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("verified_c"), dict)
            or not isinstance(manifest.get("binaries"), list)):
        reject("preserved_manifest_malformed", "Expected selection schema_version=1 and binary/verified_c collections.")
    bindings = [item for item in manifest["binaries"] if isinstance(item, dict)
                and (item.get("slug") == slug or item.get("repo_path") == donor["repo_path"])]
    if len(bindings) != 1 or bindings[0].get("slug") != slug or bindings[0].get("repo_path") != donor["repo_path"]:
        reject("preserved_donor_binding_ambiguous", "Manifest must bind the consumed donor repo path and slug uniquely.")
    entries = manifest["verified_c"].get(slug, [])
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        reject("preserved_manifest_malformed", "Donor verified_c entries must be objects.")
    matches = [item for item in entries if item.get("original_source") == recorded_path
               and item.get("name") == source_name]
    if len(matches) != 1:
        reject("preserved_join_missing" if not matches else "preserved_join_ambiguous",
               "Expected one exact original_source and name match within the bound donor.")
    item = matches[0]
    address = item.get("address")
    if (not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]{1,16}", address)
            or not 0 < int(address, 16) <= 0x7fffffffffffffff):
        reject("preserved_address_invalid", "Selection row lacks a valid donor address.")
    if "selected_address" in donor and donor["selected_address"] != int(address, 16):
        reject("preserved_address_invalid", "Frozen donor function address disagrees with selection row.")
    if sum(entry.get("address") == address for entry in entries) != 1 or manifest.get("duplicate_address"):
        reject("preserved_join_ambiguous", "Donor address has multiple selected rows.")
    declared_hash = item.get("sha256")
    if not isinstance(declared_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", declared_hash):
        reject("preserved_hash_invalid", "Selection SHA-256 must be canonical lowercase hexadecimal.")
    safe_name = re.sub(r"[^A-Za-z0-9_.+-]", "_", source_name).strip("._") or "unnamed"
    filename = f"{int(address, 16):08x}_{safe_name}.c"
    if item.get("path") != f"src/{slug}/verified_c/{filename}":
        reject("preserved_path_invalid", "Selection path must match its donor slug, address and safe name.")
    materialized = Path(selection.materialized_binaries_root)
    try:
        materialized.relative_to(root)
        if materialized.resolve(strict=True) != materialized or not materialized.is_dir():
            raise ValueError("Materialized root changed or is not a directory.")
    except (OSError, RuntimeError, ValueError) as exc:
        reject("preserved_root_invalid", str(exc))
    path = materialized / slug / "source" / "verified_c" / filename
    resolved, reason, detail = _resolve_source_file(materialized, str(path))
    if resolved is None:
        reject("preserved_" + reason, detail)
    assert resolved is not None
    return resolved, json.dumps(item, sort_keys=True, separators=(",", ":"))


def _preserved_join_index(manifest: Any) -> tuple[
    dict[tuple[str, str, str], dict[str, Any]], dict[str | None, Any],
]:
    """Index exact selection joins once; malformed donor lists stay excluded."""
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("verified_c"), dict)
            or not isinstance(manifest.get("binaries"), list)):
        return {}, {None: manifest}
    binaries = manifest["binaries"]
    by_slug: dict[str, list[dict[str, Any]]] = {}
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for binary in binaries:
        if (not isinstance(binary, dict) or not isinstance(binary.get("slug"), str)
                or not binary["slug"] or not isinstance(binary.get("repo_path"), str)
                or not binary["repo_path"]):
            raise KotorXIDSourceError(
                "preserved_manifest_malformed: every binary row requires nonempty slug and repo_path strings."
            )
        by_slug.setdefault(binary["slug"], []).append(binary)
        by_repo.setdefault(binary["repo_path"], []).append(binary)
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    missing: dict[str | None, Any] = {
        None: {"schema_version": 1, "binaries": [], "verified_c": {}},
    }
    for slug in by_slug.keys() | manifest["verified_c"].keys():
        entries = manifest["verified_c"].get(slug, [])
        bound = list(by_slug.get(slug, []))
        # Include conflicting repo bindings as well as conflicting slug rows.
        for binary in tuple(bound):
            for other in by_repo.get(binary["repo_path"], []):
                if other not in bound:
                    bound.append(other)
        entries_valid = isinstance(entries, list) and all(isinstance(item, dict) for item in entries)
        # A compact sentinel preserves malformed-list diagnostics. Misses never
        # revisit the complete donor list, including for malformed inputs.
        missing[slug] = {
            "schema_version": 1, "binaries": bound,
            "verified_c": {slug: [] if entries_valid else None},
        }
        if not entries_valid:
            continue
        address_counts: dict[int, int] = {}
        joins: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for item in entries:
            address = item.get("address")
            if isinstance(address, str) and re.fullmatch(r"0x[0-9a-fA-F]{1,16}", address):
                numeric_address = int(address, 16)
                address_counts[numeric_address] = address_counts.get(numeric_address, 0) + 1
            original, name = item.get("original_source"), item.get("name")
            if isinstance(original, str) and isinstance(name, str):
                joins.setdefault((slug, original, name), []).append(item)
        for key, matches in joins.items():
            result[key] = {
                "schema_version": 1, "binaries": bound,
                "verified_c": {slug: matches},
                "duplicate_address": any(address_counts.get(int(item["address"], 16), 0) > 1
                                         for item in matches if isinstance(item.get("address"), str)
                                         and re.fullmatch(r"0x[0-9a-fA-F]{1,16}", item["address"])),
            }
    return result, missing


def _unique_manifest_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise KotorXIDSourceError(f"preserved_manifest_malformed: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _schema_snapshot(connection: sqlite3.Connection) -> tuple[str, tuple[str, ...]]:
    tables = {
        str(row[0]): str(row[1] or "")
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    schema_rows: list[tuple[str, str, tuple[tuple[Any, ...], ...]]] = []
    for table in sorted(_REQUIRED_COLUMNS):
        if table not in tables:
            raise KotorXIDSourceError(f"KotorXID source is missing required table {table!r}.")
        # Table names are fixed constants above, not user-provided SQL.
        info = tuple(tuple(row) for row in connection.execute(f'PRAGMA table_info("{table}")'))
        names = {str(row[1]) for row in info}
        missing = sorted(_REQUIRED_COLUMNS[table] - names)
        if missing:
            raise KotorXIDSourceError(
                f"KotorXID table {table!r} lacks required consumed columns: {', '.join(missing)}."
            )
        schema_rows.append((table, tables[table], info))

    fingerprint = hashlib.sha256(
        json.dumps(schema_rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    migration_tables = tuple(
        name for name in sorted(tables) if "migration" in name.casefold()
    )
    return fingerprint, migration_tables


def resolve_kotorxid_candidates(
    database_path: str | Path,
    *,
    target_repo_path: str,
    selected_target_sha256: str,
    selected_target_md5: str,
    allowed_source_root: str | Path,
    preserved_selection_manifest: str | Path | None = None,
    materialized_binaries_root: str | Path | None = None,
) -> KotorXIDCandidateSource:
    """Read candidate rows from an explicitly selected KX DB without mutation.

    ``selected_target_sha256`` pins the caller's selected AgentDecompile
    artifact; it is not proof. The selected target MD5 is compared to KX's
    descriptive row only to scope proposals. Only the exact K1 GOG repository
    row is accepted by this adapter.

    Both preserved-input arguments are required to opt into the documented
    ``<root>/<donor slug>/source/verified_c`` materialization layout. Only a
    genuinely missing recorded path may use this historical proposal input.
    """
    if target_repo_path != K1_GOG_REPO_PATH:
        raise KotorXIDSourceError(
            f"This candidate adapter accepts only {K1_GOG_REPO_PATH!r}."
        )
    digest = str(selected_target_sha256).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise KotorXIDSourceError("Selected target SHA-256 must be 64 hexadecimal characters.")
    md5 = str(selected_target_md5).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", md5):
        raise KotorXIDSourceError("Selected target MD5 must be 32 hexadecimal characters.")
    try:
        canonical = Path(database_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise KotorXIDSourceError(f"Cannot canonicalize explicit KotorXID database path: {exc}") from exc
    try:
        source_root = Path(allowed_source_root).expanduser().resolve(strict=True)
        if not source_root.is_dir():
            raise OSError("not a directory")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise KotorXIDSourceError(f"Explicit allowed KotorXID source root is unavailable: {exc}") from exc

    if (preserved_selection_manifest is None) != (materialized_binaries_root is None):
        raise KotorXIDSourceError("Preserved selection manifest and materialized binaries root must be selected together.")
    selection: PreservedSelectionSnapshot | None = None
    manifest: dict[str, Any] = {}
    manifest_path: Path | None = None
    if preserved_selection_manifest is not None:
        try:
            manifest_path = Path(preserved_selection_manifest).expanduser().resolve(strict=True)
            materialized_input = Path(materialized_binaries_root).expanduser()
            Path(os.path.abspath(materialized_input)).relative_to(source_root)
            materialized_root = materialized_input.resolve(strict=True)
            materialized_root.relative_to(source_root)
            if not materialized_root.is_dir():
                raise ValueError("Materialized binaries root must be a directory.")
            manifest_hash = _hash_source_file(manifest_path)
            manifest_bytes = _read_pinned_bytes(manifest_path, manifest_hash[3], manifest_hash[0])
            manifest = json.loads(manifest_bytes, object_pairs_hook=_unique_manifest_object)
        except (_CandidateSourceReadError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise KotorXIDSourceError(f"preserved_manifest_unavailable_or_malformed: {exc}") from exc
    preserved_index, preserved_missing = _preserved_join_index(manifest)
    donor_index: dict[str, list[dict[str, Any]]] = {}

    before = _stat_identity(canonical)
    uri = canonical.as_uri() + "?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        schema_fingerprint, migration_tables = _schema_snapshot(connection)
        if schema_fingerprint != KX_CANDIDATE_SCHEMA_FINGERPRINT:
            raise KotorXIDSourceError(
                "KotorXID consumed-table schema fingerprint does not match the reviewed candidate-source profile."
            )
        observed_user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        observed_data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])

        targets = connection.execute(
            "SELECT id, repo_path, slug, md5 FROM binary WHERE repo_path=? LIMIT 2",
            (K1_GOG_REPO_PATH,),
        ).fetchall()
        if len(targets) != 1:
            state = "missing" if not targets else "ambiguous"
            raise KotorXIDSourceError(
                f"KotorXID target row is {state}; expected one binary for {K1_GOG_REPO_PATH!r}."
            )
        target = targets[0]
        if str(target["md5"] or "").strip().lower() != md5:
            raise KotorXIDSourceError(
                "Selected target MD5 does not match the KotorXID binary row; candidate source rejected."
            )
        target_id = int(target["id"])
        if manifest_path is not None:
            # Freeze all consumed donor identities in the same SQLite snapshot;
            # src_program identifies a donor, never the selected target's slug.
            donor_binaries = [dict(row) for row in connection.execute(
                "SELECT id, repo_path, slug, md5 FROM binary ORDER BY id"
            )]
            for donor in donor_binaries:
                for program in {donor["repo_path"], Path(donor["repo_path"]).name}:
                    donor_index.setdefault(program, []).append(donor)
            selection = PreservedSelectionSnapshot(
                manifest_path=str(manifest_path), manifest_sha256=manifest_hash[0],
                manifest_stat=manifest_hash[3],
                materialized_binaries_root=str(materialized_root),
            )
        proposals = connection.execute(
            """SELECT r.dst_addr, r.dst_name, r.size AS reuse_size, r.real_c AS reuse_real_c,
                      r.basis, r.src_program, r.src_name,
                      s.path AS source_path, s.evidence AS source_evidence,
                      s.real_c AS source_real_c,
                      f.name AS function_name, f.size AS func_size,
                      f.canon_key, f.calling_convention
                 FROM reuse_candidate AS r
                 JOIN binary AS b ON b.id=r.dst_binary_id
                 JOIN func AS f ON f.binary_id=r.dst_binary_id AND f.addr=r.dst_addr
                 JOIN recovered_function AS s
                   ON s.program=r.src_program AND s.name=r.src_name
                WHERE b.id=? AND b.repo_path=?
                ORDER BY r.dst_addr, r.src_program, r.src_name""",
            (target_id, K1_GOG_REPO_PATH),
        ).fetchall()

        # Preserved fallback also consumes donor function cardinality. Freeze
        # only referenced keys under this same transaction before resolving or
        # hashing filesystem sources. Keep up to two rows to retain ambiguity.
        donor_function_snapshot: dict[tuple[int, int], list[sqlite3.Row]] = {}
        for row in proposals:
            if selection is None or not bool(row['reuse_real_c']) or not bool(row['source_real_c']):
                continue
            donors = donor_index.get(str(row['src_program']), [])
            if len(donors) != 1:
                continue
            slug = donors[0]['slug']
            selected = preserved_index.get((slug, str(row['source_path']), str(row['src_name'])))
            entries = selected.get('verified_c', {}).get(slug) if isinstance(selected, dict) else None
            if not isinstance(entries, list) or len(entries) != 1:
                continue
            address = entries[0].get('address')
            if (not isinstance(address, str) or not re.fullmatch(r'0x[0-9a-fA-F]{1,16}', address)
                    or not 0 < int(address, 16) <= 0x7fffffffffffffff):
                continue
            key = (int(donors[0]['id']), int(address, 16))
            if key not in donor_function_snapshot:
                donor_function_snapshot[key] = connection.execute(
                    'SELECT addr, name, size FROM func WHERE binary_id=? AND addr=? LIMIT 2', key,
                ).fetchall()
        # SQLite supplies consistent rows/schema even if unrelated writers
        # commit later. Do not hold a read transaction through source hashing.
        connection.commit()

        seen: set[tuple[int, str, str]] = set()
        candidates: list[CandidateProposal] = []
        exclusions: list[CandidateExclusion] = []
        source_hash_cache: dict[
            str, tuple[str, str, int, tuple[int, int, int, int, int]]
        ] = {}
        for row in proposals:
            key = (int(row["dst_addr"]), str(row["src_program"]), str(row["src_name"]))
            if key in seen:
                raise KotorXIDSourceError(
                    "KotorXID candidate join produced duplicate target/source identities; refusing ambiguous proposals."
                )
            seen.add(key)
            recorded_source_path = str(row["source_path"])
            if not bool(row["reuse_real_c"]) or not bool(row["source_real_c"]):
                failed_flags = []
                if not bool(row["reuse_real_c"]):
                    failed_flags.append("reuse_candidate.real_c is false")
                if not bool(row["source_real_c"]):
                    failed_flags.append("recovered_function.real_c is false")
                exclusions.append(CandidateExclusion(
                    target_address=key[0], source_program=key[1], source_name=key[2],
                    recorded_source_path=recorded_source_path,
                    reason_code="candidate_not_verified_readable_c",
                    detail="; ".join(failed_flags),
                ))
                continue
            source_file, source_path_reason, source_path_detail = _resolve_source_file(
                source_root, recorded_source_path
            )
            preserved_row_json = None
            preserved_donor_json = None
            declared_source_sha256 = None
            if source_file is None and source_path_reason == "source_file_missing" and selection is not None:
                try:
                    donors = donor_index.get(key[1], [])
                    donor_slug = donors[0]["slug"] if len(donors) == 1 else ""
                    selected_manifest = preserved_index.get((donor_slug, recorded_source_path, key[2]))
                    if selected_manifest is None:
                        selected_manifest = preserved_missing.get(donor_slug, preserved_missing[None])
                    source_file, preserved_row_json = _resolve_preserved_source(
                        source_root, selection, selected_manifest, donors, key[1], key[2], recorded_source_path,
                    )
                    declared_source_sha256 = json.loads(preserved_row_json)["sha256"]
                    donor_address = int(json.loads(preserved_row_json)["address"], 16)
                    donor_functions = donor_function_snapshot.get((int(donors[0]['id']), donor_address), [])
                    if len(donor_functions) != 1:
                        raise _CandidateSourceReadError(
                            "preserved_donor_address_unbound",
                            "Selection address must identify one function in the consumed donor binary.",
                        )
                    preserved_donor_json = json.dumps({
                        **donors[0], "selected_address": donor_address,
                        "selected_function": dict(donor_functions[0]),
                    }, sort_keys=True, separators=(",", ":"))
                except _CandidateSourceReadError as exc:
                    source_file = None
                    source_path_reason, source_path_detail = exc.reason_code, exc.detail
            if source_file is None:
                exclusions.append(CandidateExclusion(
                    target_address=key[0], source_program=key[1], source_name=key[2],
                    recorded_source_path=recorded_source_path,
                    reason_code=source_path_reason,
                    detail=source_path_detail,
                ))
                continue
            source_hash = source_hash_cache.get(str(source_file))
            if source_hash is None:
                try:
                    source_hash = _hash_source_file(source_file)
                except _CandidateSourceReadError as exc:
                    exclusions.append(CandidateExclusion(
                        target_address=key[0], source_program=key[1], source_name=key[2],
                        recorded_source_path=recorded_source_path,
                        reason_code=exc.reason_code,
                        detail=exc.detail,
                    ))
                    continue
                source_hash_cache[str(source_file)] = source_hash
            if declared_source_sha256 is not None and source_hash[0] != declared_source_sha256:
                exclusions.append(CandidateExclusion(
                    target_address=key[0], source_program=key[1], source_name=key[2],
                    recorded_source_path=recorded_source_path,
                    reason_code="preserved_source_hash_mismatch",
                    detail="Materialized bytes disagree with the selected historical manifest hash.",
                ))
                continue
            target_size = int(row["func_size"]) if row["func_size"] is not None else None
            reuse_size = int(row["reuse_size"]) if row["reuse_size"] is not None else None
            if target_size is None or reuse_size is None:
                reason_codes = ("candidate_or_target_size_unavailable",)
            elif target_size != reuse_size:
                reason_codes = ("candidate_target_size_mismatch",)
            else:
                reason_codes = ()
            if row["dst_name"] != row["function_name"]:
                reason_codes += ("candidate_name_disagrees_with_target_function",)
            work_item_key = hashlib.sha256(json.dumps({
                "target_sha256": digest,
                "candidate_key": key,
                "source_sha256": source_hash[0],
                "source_kind": "preserved_selection" if preserved_row_json is not None else "recorded_source",
                "preserved_manifest_sha256": selection.manifest_sha256 if preserved_row_json is not None else None,
                "preserved_row_json": preserved_row_json,
                "preserved_donor_json": preserved_donor_json,
                "schema_fingerprint": schema_fingerprint,
                "target_name": row["dst_name"],
                "function_name": row["function_name"],
                "target_size": target_size,
                "reuse_size": reuse_size,
                "target_canonical_key": row["canon_key"],
                "target_calling_convention": row["calling_convention"],
                "reuse_basis": row["basis"],
            }, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
            candidates.append(CandidateProposal(
                target_address=key[0],
                target_name=str(row["dst_name"]) if row["dst_name"] is not None else None,
                function_name=(str(row["function_name"]) if row["function_name"] is not None else None),
                target_size=target_size,
                reuse_size=reuse_size,
                target_canonical_key=(str(row["canon_key"]) if row["canon_key"] is not None else None),
                target_calling_convention=(
                    str(row["calling_convention"]) if row["calling_convention"] is not None else None
                ),
                source_program=key[1],
                source_name=key[2],
                source_path=str(source_file),
                recorded_source_path=recorded_source_path,
                source_file_sha256=source_hash[0],
                source_file_identity=source_hash[1],
                source_file_stat=source_hash[3],
                source_evidence=(str(row["source_evidence"]) if row["source_evidence"] is not None else None),
                source_real_c=bool(row["source_real_c"]),
                reuse_real_c=bool(row["reuse_real_c"]),
                basis=str(row["basis"]),
                work_item_key=work_item_key,
                source_kind="preserved_selection" if preserved_row_json is not None else "recorded_source",
                preserved_selection=selection if preserved_row_json is not None else None,
                preserved_row_json=preserved_row_json,
                preserved_donor_json=preserved_donor_json,
                declared_source_sha256=declared_source_sha256,
                provenance=("reuse_candidate", "recovered_function", "func", "binary") + (
                    ("preserved_selection_manifest", "historical_materialization_hash")
                    if preserved_row_json is not None else ()
                ),
                reason_codes=reason_codes,
            ))
    except KotorXIDSourceError:
        raise
    except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
        raise KotorXIDSourceError(
            f"Explicit KotorXID source is unreadable or does not satisfy the candidate contract: {exc}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    # Content, size, timestamp and WAL/SHM churn are refreshable diagnostics.
    # Replacement of the explicitly selected main file/path is a different DB.
    after = _one_file_identity(canonical)
    if (Path(database_path).expanduser().resolve(strict=True) != canonical
            or before[0][:2] != after[:2]):
        raise KotorXIDSourceError(
            "Explicit KotorXID database path or main-file physical identity changed during the snapshot read."
        )
    if selection is not None and _one_file_identity(Path(selection.manifest_path)) != selection.manifest_stat:
        raise KotorXIDSourceError("Preserved selection changed during candidate resolution; discard this snapshot.")
    identity_data = {
        "path": str(canonical),
        "stat": before,
        "schema": schema_fingerprint,
        "user_version_observed": observed_user_version,
        "data_version_observed": observed_data_version,
        "sqlite_sidecars": before[1:],
        "target_id": target_id,
        "target_slug": str(target["slug"]),
        "target_sha256_caller_selected": digest,
        "target_md5_caller_selected": md5,
        "preserved_selection": None if selection is None else {
            "manifest_path": selection.manifest_path,
            "manifest_sha256": selection.manifest_sha256,
            "manifest_stat": selection.manifest_stat,
            "materialized_binaries_root": selection.materialized_binaries_root,
            "donor_binaries": donor_binaries,
        },
    }
    file_identity = hashlib.sha256(
        json.dumps(identity_data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return KotorXIDCandidateSource(
        database_path=str(canonical),
        database_size=before[0][2],
        allowed_source_root=str(source_root),
        file_identity=file_identity,
        schema_fingerprint=schema_fingerprint,
        observed_user_version=observed_user_version,
        observed_data_version=observed_data_version,
        sqlite_sidecar_identity=before[1:],
        observed_migration_tables=migration_tables,
        target_repo_path=K1_GOG_REPO_PATH,
        target_binary_id=target_id,
        target_slug=str(target["slug"]),
        selected_target_sha256=digest,
        selected_target_md5=md5,
        candidates=tuple(candidates),
        exclusions=tuple(exclusions),
        preserved_selection=selection,
        preserved_manifest_bytes_hex=manifest_bytes.hex() if selection is not None else None,
        preserved_donor_binaries_json=(json.dumps(donor_binaries, sort_keys=True, separators=(",", ":"))
                                       if selection is not None else None),
    )
