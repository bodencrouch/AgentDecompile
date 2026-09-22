"""Declare the basis a hook pack is deterministic against, and check it.

"Same inputs, same bytes" is only meaningful relative to a declared basis:
which analyzer produced the analysis, which algorithm and masking rules ran,
which thresholds applied, and which corpus images were declared. Every pack
carries this object at its root so a re-run can be compared under an
identical basis.

Every field is a pure function of store-recorded values (``binary`` rows)
or pinned package constants. Nothing in :func:`basis` reads the process
environment: the analyzer identity is captured once at ingest
(``extract.stamp_analyzer_identity``) or by the ``analyzer_identity``
backfill pass, and only those two paths may consult the install.

Fields whose producing unit has not landed are named in
:data:`PENDING_FIELDS`. They are omitted from the object and listed under
``basis.pending``. Every other field must be present, non-empty and not
``"unknown"``; :func:`basis` raises :class:`BasisError` otherwise. Removing a
name from ``PENDING_FIELDS`` is the landing unit's versioned change.

Per-binary ``basis_hash`` is ``sha256`` over the object minus
:data:`BASIS_HASH_EXCLUDED` -- the corpus manifest and anything else derived
from corpus membership. ``analyzer.processor_spec_hash`` is excluded because
it hashes the *set* of language ids in the store and a multi-architecture
corpus is normal (``cross_arch`` is a pair class). So "mixed" detects a
differing analyzer version or differing package constants, never mixed
architectures. ``schema_migration.basis_hash`` records the same hash.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import tempfile
from pathlib import Path

#: Version of the basis object itself. v1 was the five-key shape
#: (decoder, algorithm_version, masking_rule_version, threshold_params,
#: corpus_manifest_hash) emitted before 3b basis hardening.
BASIS_VERSION = 2

#: Names the cascade revision and the tie-break key it orders by.
ALGORITHM_VERSION = "phase0.2+key:content_sha256"

#: Present but "none" until U4 lands a masking rule set.
MASKING_RULE_VERSION = "none"

#: Pinned until U54 records the analyzer option set per build.
ANALYZER_OPTIONS_HASH = "pinned:headless-defaults"
#: Pinned until U65 lands a timeout policy.
ANALYZER_TIMEOUT_POLICY = "pinned:none"
#: Pinned until U54 records the loader revision per build.
ANALYZER_LOADER_REVISION = "pinned:unversioned"
#: Pinned until U54 records per-build toolchain identity; ``binary`` has no
#: toolchain columns yet.
TOOLCHAIN_IDENTITY_HASH = "pinned:none"

#: Dotted names of basis fields with no producer on this branch. Sorted.
PENDING_FIELDS = (
    "analyzer.compiler_spec_ids",  # extractor reads it; no binary column, no project-free backfill
    "data_packs",  # U19a
    "decoder",  # U4 picks the decoder; binary.decoder_revision stays NULL
    "external_channels.bsim_generator_revision",  # U5d
    "filler_set",  # U58
    "threshold_params.divergence",  # U14
)

#: Dotted names left out of ``basis_hash``: anything derived from corpus
#: membership, so two builds ingested into different stores under one
#: install carry the same hash.
BASIS_HASH_EXCLUDED = ("corpus_manifest_hash", "analyzer.processor_spec_hash")

#: Values that count as absent.
_ABSENT = (None, "", "unknown")


class BasisError(ValueError):
    """The store cannot declare a complete, single basis."""


# --- ingest / backfill helpers (the only environment reads in this module) ---


def install_analyzer_version(install_dir: str | os.PathLike | None = None) -> str | None:
    """Analyzer version string of an install, or None when it cannot be read.

    Reads ``application.properties`` under *install_dir* (default: the
    ``GHIDRA_INSTALL_DIR`` environment variable). Called at ingest and by the
    ``analyzer_identity`` backfill pass only; :func:`basis` never calls it.
    """
    install = str(install_dir or os.environ.get("GHIDRA_INSTALL_DIR", "")).strip()
    if not install:
        return None
    props = Path(install) / "Ghidra" / "application.properties"
    try:
        for line in props.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("application.version="):
                value = line.split("=", 1)[1].strip()
                return value or None
    except OSError:
        pass
    return None


def processor_spec_hash_for(language_id: str | None) -> str | None:
    """Per-binary processor-spec identity from its language id.

    A stand-in for a hash over the processor specification files: it still
    pins which language definition the analysis ran under. None when the
    language id is unknown.
    """
    text = str(language_id or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --- the object ------------------------------------------------------------


def seeds() -> dict:
    """Every fixed seed the cascade and its evaluators mix in."""
    from . import bsim_eval, cfg_signature

    sample_seed = inspect.signature(bsim_eval.evaluate_pairs).parameters["seed"].default
    return {
        "bsim_eval_sample": int(sample_seed),
        "cfg_signature": {
            "golden": f"0x{cfg_signature._GOLDEN:016x}",
            "seed": f"0x{cfg_signature._SEED:016x}",
        },
    }


def _check_present(value, path: str) -> None:
    """Raise BasisError naming the first absent, empty or "unknown" leaf."""
    if value in _ABSENT:
        raise BasisError(f"basis: {path} is absent")
    if isinstance(value, dict):
        if not value:
            raise BasisError(f"basis: {path} is empty")
        for k in sorted(value):
            _check_present(value[k], f"{path}.{k}")
    elif isinstance(value, list):
        if not value:
            raise BasisError(f"basis: {path} is empty")
        for i, v in enumerate(value):
            _check_present(v, f"{path}[{i}]")


def _without(obj: dict, dotted: tuple[str, ...]) -> dict:
    out = json.loads(json.dumps(obj, sort_keys=True))
    for name in dotted:
        parts = name.split(".")
        node = out
        for p in parts[:-1]:
            node = node.get(p) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(parts[-1], None)
    return out


def package_basis(analyzer_version: str | None) -> dict:
    """The store-independent part of the basis for one analyzer version.

    This is exactly what ``basis_hash`` covers: the object minus
    :data:`BASIS_HASH_EXCLUDED`. Raises :class:`BasisError` when anything is
    absent, so an ingest under an unreadable install cannot stamp a hash.
    """
    from .policy_tables import threshold_params

    obj = {
        "basis_version": BASIS_VERSION,
        "analyzer": {
            "version": analyzer_version,
            "options_hash": ANALYZER_OPTIONS_HASH,
            "timeout_policy": ANALYZER_TIMEOUT_POLICY,
            "loader_revision": ANALYZER_LOADER_REVISION,
        },
        "algorithm_version": ALGORITHM_VERSION,
        "masking_rule_version": MASKING_RULE_VERSION,
        "threshold_params": threshold_params(),
        "seeds": seeds(),
        "toolchain_identity_hash": TOOLCHAIN_IDENTITY_HASH,
        "pending": sorted(PENDING_FIELDS),
    }
    _check_present({k: v for k, v in obj.items() if k != "pending"}, "$")
    return obj


def basis_hash_for(analyzer_version: str | None) -> str:
    payload = json.dumps(package_basis(analyzer_version), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def corpus_manifest_hash(con) -> str:
    """sha256 over the sorted per-image identities, one per line.

    content_sha256 is the identity; md5 stands in when it is missing; the slug
    is the last resort so an image with no recorded hash still counts.
    Blank strings are treated as missing.

    Scope (A4): once ``corpus admit`` has run, only admitted rows are in the
    manifest -- placeholders, duplicates, contested and unresolved rows are
    outside the key by design. Before admission (pre-migration store, or
    migrated but never admitted) every row counts, as before.
    """
    from .admission import admitted_predicate

    rows = con.execute(
        "SELECT COALESCE(NULLIF(TRIM(content_sha256), ''), NULLIF(TRIM(md5), ''), slug) FROM binary"
        " WHERE 1=1" + admitted_predicate(con, "binary")
    ).fetchall()
    manifest = sorted(str(r[0]) for r in rows)
    return hashlib.sha256("\n".join(manifest).encode("utf-8")).hexdigest()


def _group(rows, key: str) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["slug"])
    return {k: sorted(v) for k, v in groups.items()}


def _fmt_groups(groups: dict) -> str:
    return "; ".join(f"{k} [{', '.join(v)}]" for k, v in sorted(groups.items(), key=lambda kv: str(kv[0])))


def _identity_rows(con) -> list[dict]:
    """Analyzer-identity columns of the rows the basis covers, by slug.

    Scope (A4): admitted rows only once ``corpus admit`` has run; every row
    before that. Placeholders are outside the basis by design. When
    admission has run and no row is admitted the basis cannot be declared,
    and that is said in the refusal rather than reported as an empty store.
    """
    from .admission import admission_scope, admitted_predicate

    cur = con.execute(
        "SELECT slug, analyzer_version, processor_spec_hash, basis_hash FROM binary"
        " WHERE 1=1" + admitted_predicate(con, "binary") + " ORDER BY slug"
    )
    names = [d[0] for d in cur.description]
    rows = [dict(zip(names, r)) for r in cur.fetchall()]
    if not rows and admission_scope(con) == "admitted":
        raise BasisError(
            "basis: no admitted builds (corpus admit ran and every analyzed row is unresolved, "
            "duplicate or contested); resolve the raw images and re-run corpus admit"
        )
    return rows


def basis(con) -> dict:
    """The declared basis of *con*, or :class:`BasisError`.

    Refuses when the store has no ``binary`` row, when any row lacks its
    analyzer identity, when rows disagree on ``analyzer_version`` or
    ``basis_hash``, when a stored ``basis_hash`` no longer matches the hash
    the current package computes (the package basis changed since ingest;
    that is the re-baseline trigger), or when any non-pending field is
    absent, empty or ``"unknown"``.
    """
    rows = _identity_rows(con)
    if not rows:
        raise BasisError("basis: analyzer.version has no producer row (store has no binary rows)")
    for column, field in (
        ("analyzer_version", "analyzer.version"),
        ("processor_spec_hash", "analyzer.processor_spec_hash"),
        ("basis_hash", "binary.basis_hash"),
    ):
        missing = sorted(r["slug"] for r in rows if r[column] in _ABSENT)
        if missing:
            raise BasisError(f"basis: {field} is absent for [{', '.join(missing)}]")
    versions = _group(rows, "analyzer_version")
    if len(versions) > 1:
        raise BasisError(f"basis: mixed analyzer.version across binary rows: {_fmt_groups(versions)}")
    hashes = _group(rows, "basis_hash")
    if len(hashes) > 1:
        raise BasisError(f"basis: mixed basis_hash across binary rows: {_fmt_groups(hashes)}")
    (version,) = versions
    (stored,) = hashes
    current = basis_hash_for(version)
    if stored != current:
        raise BasisError(
            f"basis: basis_hash drift for [{', '.join(hashes[stored])}]: stored {stored} != current {current} "
            "(package basis changed since ingest; re-baseline)"
        )
    obj = package_basis(version)
    spec_hashes = sorted({str(r["processor_spec_hash"]) for r in rows})
    obj["analyzer"]["processor_spec_hash"] = hashlib.sha256("\n".join(spec_hashes).encode("utf-8")).hexdigest()[:16]
    obj["corpus_manifest_hash"] = corpus_manifest_hash(con)
    return {k: obj[k] for k in sorted(obj)}


def basis_hash(con) -> str:
    """``sha256`` of :func:`basis` minus :data:`BASIS_HASH_EXCLUDED`.

    The same value every ``binary`` row of a coherent store carries and the
    migration ledger records.
    """
    payload = json.dumps(_without(basis(con), BASIS_HASH_EXCLUDED), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- verification ----------------------------------------------------------


def _copy_store(src: Path, dst: Path) -> None:
    # Backup API, not a file copy: the store runs in WAL mode, so a plain copy
    # of the main file can miss committed rows. Read-only URI never touches src.
    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def first_diff_path(a, b, path: str = "$") -> str:
    """Path of the first differing JSON node, walking keys in sorted order."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}"
            sub = first_diff_path(a[k], b[k], f"{path}.{k}")
            if sub:
                return sub
        return ""
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            sub = first_diff_path(x, y, f"{path}[{i}]")
            if sub:
                return sub
        return f"{path}[{min(len(a), len(b))}]" if len(a) != len(b) else ""
    return "" if a == b else path


def verify_export(db: Path, export) -> dict:
    """Run *export(con, out)* against two temp copies of *db* and byte-diff.

    Returns {"identical": bool, "diff": <first differing key path or "">}.
    A :class:`BasisError` from the export propagates: a store that cannot
    declare its basis has nothing to verify.
    """
    from .store import connect

    with tempfile.TemporaryDirectory() as tmp:
        outs = []
        for tag in ("a", "b"):
            copy = Path(tmp) / f"{tag}.sqlite"
            _copy_store(Path(db), copy)
            out = Path(tmp) / f"{tag}.json"
            export(connect(copy), out)
            outs.append(out.read_bytes())
    if outs[0] == outs[1]:
        return {"identical": True, "diff": ""}
    path = first_diff_path(json.loads(outs[0]), json.loads(outs[1]))
    return {"identical": False, "diff": path or "$ (serialization only)"}
