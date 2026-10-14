"""``compile-attempt``: one translation unit, one era-exact compiler invocation (design §3.3, §4).

Inputs: ``tu`` -- the self-contained TU text object (header + body; the bulk path already emits
header-free text, ghidra_bulk.py:622-626).  Params: ``toolchain_identity_hash`` (the content
hash of the toolchain's declared manifest, ``toolchain.identity_hash_for``, U132), ``profile``,
``opt`` (``/O2``), ``flags`` (extra compiler flags).  The toolchain itself is **never** an input: a node maps the hash to a local tree it
proved by canary (``register_toolchain``), and a task whose hash it cannot resolve is refused by
name before any input is fetched.  Capability: ``toolchain:<toolchain_identity_hash>``.

Output: on a compiler success ``obj`` (the COFF bytes) + ``receipt`` ``{outcome: "obj",
obj_sha256, masked_coff_sha256, ...}``; on a compiler error ``diagnostics`` (scrubbed compiler
text) + ``receipt`` ``{outcome: "diag", diagnostic_codes: [...]}``.  INFRA (timeout, no object
and no diagnostic) raises ``Infra`` and writes nothing, so the task stays in the frontier.

Verification (``verify``): recompute on this node with the same toolchain hash and compare the
masked-COFF hash (COFF ``TimeDateStamp`` zeroed; ``/Zi`` forbidden), the O2 check the join
canary measures continuously; a node without the toolchain answers UNVERIFIABLE, never REFUTED.
Budget SMALL (ESTIMATE 0.3-2 s per attempt; the class deadline is the 60 s guard the bulk path
already uses, ghidra_bulk.py:962-976).

The compile path is the existing wrapper ``scripts/cl-compile.sh <in.c> <out.obj> [flags]``
(env ``VC_ROOT``, ``WINEPREFIX``, ``CL_OPT``), which renames the source to ``in.c`` in a fresh
temp dir so the embedded file record is machine-invariant.

Acceptance tests (named, landed with U133/U132):

* ``test_compile_same_tu_same_task_id_two_nodes``;
* ``test_compile_masked_coff_equal_across_timestamps`` -- two objects differing only in
  ``TimeDateStamp`` hash equal;
* ``test_compile_toolchain_identity_path_and_mtime_free`` -- two copies of the tree at different
  paths/mtimes give one hash; one flipped byte changes it;
* ``test_compile_missing_toolchain_refuses_by_name`` -- ``Refused("toolchain-not-present:...")``
  before any object fetch;
* ``test_compile_infra_writes_nothing``;
* ``test_compile_receipt_has_no_path_and_no_slug``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    ObjectRef,
    ObjectStore,
    Refused,
    Registry,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    VerificationOutcome,
    digest,
    task_kind,
)
from agentdecompile_grid.objects.base import IntegrityError, InvalidRef, validate_ref
from agentdecompile_grid.view.applier import ensure_tables, view_hook

from .toolchain import ToolchainManifest, manifest_for_root, verify_tree
from ._common import (
    PlannableKind,
    Infra,
    assert_portable,
    check_kind,
    deadline_for,
    get_json,
    make_result,
    materialize_object,
    put_json,
    require_input,
    require_param,
    run_argv,
    scrub_paths,
)

RECEIPT_SCHEMA = "agentdecompile.grid.compile-attempt.v1"
CAPABILITY_PREFIX = "toolchain:"
DEFAULT_OPT = "/O2"
FORBIDDEN_FLAGS = ("/Zi", "/ZI", "/Z7")   # debug records make bytes machine-variant
_DIAG_CODE = re.compile(r"\b(?:error|warning|fatal error) (C\d{4})\b")


# --------------------------------------------------------------------------- toolchain identity
@dataclasses.dataclass(frozen=True)
class ToolchainRoot:
    """A local toolchain tree a node proved by canary: where it is and what it hashes to."""

    root: Path
    identity_hash: str
    script: Path
    wineprefix: Path | None = None
    files: int = 0

    def env(self, opt: str) -> dict[str, str]:
        env = dict(os.environ)
        env["VC_ROOT"] = str(self.root)
        if self.wineprefix is not None:
            env["WINEPREFIX"] = str(self.wineprefix)
        env["CL_OPT"] = opt
        env.setdefault("WINEDEBUG", "-all")
        return env


#: identity_hash -> ToolchainRoot, filled by the worker's canary (``register_toolchain``).
TOOLCHAINS = Registry("toolchain root")
_IDENTITY_CACHE: dict[str, tuple[str, int]] = {}


def toolchain_identity(root: str | Path) -> tuple[str, int]:
    """``(identity_hash, entry count)`` of the tree's manifest: path- and mtime-free (U132).

    The identity is ``toolchain.identity_hash_for`` over the declared manifest -- the in-tree
    ``toolchain-manifest.json`` when the tree carries one, else a manifest declared from every
    regular file's bytes.  Only ``(relative path, sha256)`` pairs enter the hash: no size, no
    mode, no time, no absolute path.  Cached per process by resolved root.
    """
    resolved = Path(root).expanduser().resolve()
    key = str(resolved)
    if key in _IDENTITY_CACHE:
        return _IDENTITY_CACHE[key]
    if not resolved.is_dir():
        raise Refused(f"toolchain-root-missing:{digest(key.encode())[:12]}")
    manifest = manifest_for_root(resolved)
    value = (manifest.identity_hash, len(manifest.entries))
    _IDENTITY_CACHE[key] = value
    return value


def default_compile_script() -> Path | None:
    env = os.environ.get("AGENT_DECOMPILE_MSVC_COMPILER", "").strip()
    if env and Path(env).is_file():
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for base in (here.parents[3], Path.cwd()):
        candidate = base / "scripts" / "cl-compile.sh"
        if candidate.is_file():
            return candidate.resolve()
    return None


def register_toolchain(root: str | Path, *, manifest: ToolchainManifest | None = None, wineprefix: str | Path | None = None,
                       script: str | Path | None = None, replace: bool = True) -> ToolchainRoot:
    """Register *root* so tasks keyed ``toolchain:<hash>`` resolve to it.

    With *manifest* (the canary's declared manifest) the identity is the manifest's and the tree
    is checked against it first (``toolchain-tree-mismatch:<hash>`` names a missing or altered
    declared file); without one the tree's own manifest (``toolchain_identity``) is used.  Files
    the manifest does not declare never enter the identity.
    """
    resolved_root = Path(root).expanduser().resolve()
    if manifest is not None:
        report = verify_tree(resolved_root, manifest)
        if not report.ok:
            raise Refused(f"toolchain-tree-mismatch:{manifest.identity_hash[:12]}:missing={len(report.missing)},mismatched={len(report.mismatched)}")
        identity, count = manifest.identity_hash, len(manifest.entries)
        _IDENTITY_CACHE[str(resolved_root)] = (identity, count)
    else:
        identity, count = toolchain_identity(resolved_root)
    resolved_script = Path(script).resolve() if script else default_compile_script()
    if resolved_script is None or not resolved_script.is_file():
        raise Refused("compile-wrapper-missing:scripts/cl-compile.sh")
    tc = ToolchainRoot(
        root=resolved_root, identity_hash=identity, script=resolved_script,
        wineprefix=Path(wineprefix).expanduser().resolve() if wineprefix else None, files=count,
    )
    TOOLCHAINS.register(identity, tc, replace=replace)
    return tc


def resolve_toolchain(identity_hash: str) -> ToolchainRoot:
    """The registered tree for *identity_hash*, or a named refusal.

    Falls back to ``AGENT_DECOMPILE_TOOLCHAIN_ROOTS`` (``os.pathsep``-separated roots, hashed on
    first use) so a node can be driven without the join canary; a hash nobody holds is refused.
    """
    if identity_hash in TOOLCHAINS:
        return TOOLCHAINS.get(identity_hash)
    for root in filter(None, os.environ.get("AGENT_DECOMPILE_TOOLCHAIN_ROOTS", "").split(os.pathsep)):
        try:
            tc = register_toolchain(root, wineprefix=os.environ.get("WINEPREFIX") or None)
        except Refused:
            continue
        if tc.identity_hash == identity_hash:
            return tc
    raise Refused(f"toolchain-not-present:{identity_hash[:12]}")


# --------------------------------------------------------------------------- masked COFF
def masked_coff_sha256(data: bytes) -> str:
    """sha256 of a COFF object with the file header's ``TimeDateStamp`` (bytes 4..8) zeroed.

    Refuses the anonymous-object / import-library header (``0000 FFFF``): those carry no COFF
    file header at that offset and are not an output of ``/c`` on a C translation unit.
    """
    if len(data) < 20:
        raise Refused("coff-too-short")
    if data[:4] == b"\x00\x00\xff\xff":
        raise Refused("coff-anonymous-object")
    masked = bytearray(data)
    masked[4:8] = b"\x00\x00\x00\x00"
    return hashlib.sha256(bytes(masked)).hexdigest()


def diagnostic_codes(text: str) -> list[str]:
    """Sorted, de-duplicated compiler diagnostic codes (``C2065`` ...): a value, never the text."""
    return sorted(set(_DIAG_CODE.findall(text)))


class _CompileBindingFailure(Exception):
    """A named contradiction or unavailable piece of verification evidence."""

    def __init__(self, reason: str, outcome: VerificationOutcome = VerificationOutcome.REFUTED):
        self.reason = reason
        self.outcome = outcome
        super().__init__(reason)


def _read_compile_evidence(objects: ObjectStore, ref: ObjectRef, role: str) -> bytes:
    try:
        validate_ref(ref)
    except InvalidRef as exc:
        raise _CompileBindingFailure(f"{role}-ref-invalid") from exc
    try:
        data = objects.get(ref)
    except IntegrityError as exc:
        raise _CompileBindingFailure(f"{role}-cas-integrity") from exc
    except (KeyError, OSError) as exc:
        raise _CompileBindingFailure(f"{role}-unavailable", VerificationOutcome.UNVERIFIABLE) from exc
    # Enforce the address even for stores whose get() does not check integrity itself.
    if ObjectRef.of_bytes(data) != ref:
        raise _CompileBindingFailure(f"{role}-cas-integrity")
    return data


def _bound_compile_receipt(
    spec: TaskSpec, result: TaskResult, objects: ObjectStore, expected: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Authenticate the receipt/spec and actual object pair; this is not a full COFF parser."""
    if result.task_id != spec.task_id:
        raise _CompileBindingFailure("task-id-mismatch")
    if result.basis_hash != spec.basis_hash:
        raise _CompileBindingFailure("result-basis-mismatch")
    if result.status != ResultStatus.OK:
        raise _CompileBindingFailure("result-not-claim")
    receipt_ref = result.outputs.get("receipt")
    if receipt_ref is None:
        raise _CompileBindingFailure("receipt-missing")
    data = _read_compile_evidence(objects, receipt_ref, "receipt")
    try:
        receipt = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise _CompileBindingFailure("receipt-malformed") from exc
    if not isinstance(receipt, dict):
        raise _CompileBindingFailure("receipt-malformed")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise _CompileBindingFailure("receipt-schema-mismatch")
    if receipt.get("kind") != CompileAttempt.name:
        raise _CompileBindingFailure("receipt-kind-mismatch")
    if type(receipt.get("kind_version")) is not int or receipt["kind_version"] != CompileAttempt.version:
        raise _CompileBindingFailure("receipt-kind-version-mismatch")
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise _CompileBindingFailure(f"receipt-{field}-mismatch")
    outcome = receipt.get("outcome")
    if outcome == "diag":
        codes = receipt.get("diagnostic_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
            raise _CompileBindingFailure("receipt-diagnostic-codes-malformed")
        return receipt, None
    if outcome != "obj":
        raise _CompileBindingFailure("receipt-outcome-invalid")
    obj_ref = result.outputs.get("obj")
    if obj_ref is None:
        raise _CompileBindingFailure("obj-missing")
    obj = _read_compile_evidence(objects, obj_ref, "obj")
    if receipt.get("obj_sha256") != digest(obj):
        raise _CompileBindingFailure("obj-sha256-mismatch")
    size = receipt.get("obj_bytes")
    if type(size) is not int or size < 0 or size != len(obj):
        raise _CompileBindingFailure("obj-bytes-mismatch")
    try:
        masked = masked_coff_sha256(obj)
    except Refused as exc:
        raise _CompileBindingFailure(exc.reason) from exc
    if receipt.get("masked_coff_sha256") != masked:
        raise _CompileBindingFailure("obj-masked-coff-mismatch")
    return receipt, masked


# --------------------------------------------------------------------------- the kind
@task_kind
class CompileAttempt(PlannableKind):
    name = "compile-attempt"
    version = 1
    basis_field_set = "toolchain"     # a toolchain change re-keys compile ids; a pin-policy change does not (§2.8)
    budget = BudgetClass.SMALL
    capabilities = (CAPABILITY_PREFIX + "<toolchain_identity_hash>",)   # template; the spec carries the value
    INPUTS: Mapping[str, str] = {"tu": "translation unit text (header + body), 2-30 KB"}
    PARAMS_SCHEMA: Mapping[str, str] = {
        "toolchain_identity_hash": "content hash of the toolchain tree (``toolchain_identity``)",
        "profile": "compiler profile name (default 'default'); part of the id",
        "opt": "optimisation flag handed to the wrapper as CL_OPT (default /O2)",
        "flags": "extra compiler flags (list); /Zi, /ZI, /Z7 are refused",
        "timeout_s": "optional kill deadline; capped at SMALL (60 s)",
    }
    OUTPUTS: Mapping[str, str] = {
        "receipt": "{outcome: obj|diag, tu_sha256, obj_sha256?, masked_coff_sha256?, diagnostic_codes?}",
        "obj": "the COFF object bytes (outcome obj)",
        "diagnostics": "scrubbed compiler diagnostics text (outcome diag)",
    }
    OUTPUT_ROLES: Mapping[str, str] = {"obj": "public", "diagnostics": "public", "receipt": "public"}   # §6.3 object role tags

    @staticmethod
    def required_capabilities(spec: TaskSpec) -> tuple[str, ...]:
        return (CAPABILITY_PREFIX + str(spec.params.get("toolchain_identity_hash", "")),)

    @staticmethod
    def flags_of(spec: TaskSpec) -> list[str]:
        flags = [str(f) for f in (spec.params.get("flags") or ())]
        bad = [f for f in flags if f in FORBIDDEN_FLAGS]
        if bad:
            raise Refused("forbidden-flag:" + ",".join(sorted(bad)))
        return flags

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        identity = str(require_param(spec, "toolchain_identity_hash", kind=self.name))
        toolchain = resolve_toolchain(identity)                      # refusal first, at 1 ms
        flags = self.flags_of(spec)
        opt = str(spec.params.get("opt") or DEFAULT_OPT)
        tu_ref = require_input(spec, "tu", kind=self.name)
        deadline = deadline_for(self.budget, spec.params.get("timeout_s"))
        started = time.monotonic()
        scratch_dir = Path(scratch)
        src = materialize_object(objects, tu_ref, scratch_dir / "in.c")
        obj_path = scratch_dir / "out.obj"
        obj_path.unlink(missing_ok=True)
        outcome = run_argv(
            ["bash", str(toolchain.script), str(src), str(obj_path), *flags],
            cwd=scratch_dir, timeout_s=deadline, env=toolchain.env(opt),
        )
        if outcome.timed_out:
            raise Infra(f"timeout:compile-attempt:{int(deadline)}s")
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA, "kind": self.name, "kind_version": self.version,
            "tu_sha256": tu_ref.hex, "toolchain_identity_hash": identity,
            "profile": str(spec.params.get("profile") or "default"), "opt": opt, "flags": flags,
            "basis_hash": spec.basis_hash,
        }
        outputs: dict[str, ObjectRef] = {}
        if outcome.returncode == 0 and obj_path.is_file() and obj_path.stat().st_size > 0:
            data = obj_path.read_bytes()
            outputs["obj"] = objects.put(data)
            receipt.update({
                "outcome": "obj", "obj_sha256": outputs["obj"].hex, "obj_bytes": len(data),
                "masked_coff_sha256": masked_coff_sha256(data),
            })
        else:
            text = scrub_paths((outcome.stderr or "") + (outcome.stdout or ""))
            codes = diagnostic_codes(text)
            if not codes and not text.strip():
                raise Infra("no-object-no-diagnostic")
            if not codes and outcome.returncode == 3:
                raise Infra("compile-wrapper-refused")   # cl.exe not found at VC_ROOT: host, not source
            outputs["diagnostics"] = objects.put(text.encode("utf-8"))
            receipt.update({
                "outcome": "diag", "diagnostic_codes": codes, "diagnostics_sha256": outputs["diagnostics"].hex,
                "compiler_exit": outcome.returncode,
            })
        assert_portable(receipt)
        outputs["receipt"] = put_json(objects, receipt)
        return make_result(
            spec, outputs, elapsed_s=time.monotonic() - started,
            metrics={"compile_wall_s": round(outcome.elapsed_s, 3), "deadline_s": deadline, "toolchain_files": toolchain.files},
        )

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        """Bind actual outputs to spec/receipt, then compare independently derived masked hashes."""
        result_ref = ObjectRef.of_value(result.to_record())
        try:
            check_kind(spec, self.name, self.version)
            try:
                tu_ref = validate_ref(require_input(spec, "tu", kind=self.name))
            except InvalidRef as exc:
                raise _CompileBindingFailure("tu-ref-invalid") from exc
            expected = {
                "tu_sha256": tu_ref.hex,
                "toolchain_identity_hash": str(require_param(spec, "toolchain_identity_hash", kind=self.name)),
                "profile": str(spec.params.get("profile") or "default"),
                "opt": str(spec.params.get("opt") or DEFAULT_OPT),
                "flags": self.flags_of(spec), "basis_hash": spec.basis_hash,
            }
            proposal, proposal_masked = _bound_compile_receipt(spec, result, objects, expected)
        except Refused as exc:
            return Verification(spec.task_id, result_ref, VerificationOutcome.REFUTED, "", "recompute",
                                {"reason": exc.reason})
        except _CompileBindingFailure as exc:
            return Verification(spec.task_id, result_ref, exc.outcome, "", "recompute", {"reason": exc.reason})
        try:
            recomputed = self.run(spec, objects, scratch)
        except Refused as exc:
            return Verification(spec.task_id, result_ref, VerificationOutcome.UNVERIFIABLE, "", "recompute",
                                {"reason": exc.reason})
        try:
            mine, recomputed_masked = _bound_compile_receipt(spec, recomputed, objects, expected)
        except _CompileBindingFailure as exc:
            return Verification(spec.task_id, result_ref, exc.outcome, "", "recompute",
                                {"reason": "recomputed-" + exc.reason})
        if proposal.get("outcome") != mine.get("outcome"):
            outcome, why = VerificationOutcome.REFUTED, "outcome-differs"
        elif mine.get("outcome") == "obj":
            same = proposal_masked == recomputed_masked
            outcome, why = (VerificationOutcome.VERIFIED, "masked-coff-equal") if same else (VerificationOutcome.REFUTED, "masked-coff-differs")
        else:
            same = proposal.get("diagnostic_codes") == mine.get("diagnostic_codes")
            outcome, why = (VerificationOutcome.VERIFIED, "diagnostic-codes-equal") if same else (VerificationOutcome.REFUTED, "diagnostic-codes-differ")
        return Verification(
            spec.task_id, result_ref, outcome, "", "recompute",
            {
                "why": why,
                "masked_coff_sha256": {"proposal": proposal_masked, "recomputed": recomputed_masked},
                "obj_sha256_equal": proposal.get("obj_sha256") == mine.get("obj_sha256"),
            },
        )

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "budget": cls.budget.value,
            "capabilities": list(cls.capabilities), "inputs": dict(cls.INPUTS), "params": dict(cls.PARAMS_SCHEMA),
            "outputs": dict(cls.OUTPUTS), "output_roles": dict(cls.OUTPUT_ROLES), "verify": "recompute; masked-COFF hash equality (TimeDateStamp zeroed)",
            "toolchains_registered": TOOLCHAINS.names(), "status": "working",
            "wrapper": "scripts/cl-compile.sh <in.c> <out.obj> [flags] (VC_ROOT, WINEPREFIX, CL_OPT)",
        }


# --------------------------------------------------------------------------- view hook
COMPILE_RECEIPT_SQL = """
CREATE TABLE IF NOT EXISTS grid_compile_receipt (
    task_id                 TEXT PRIMARY KEY,
    tu_sha256               TEXT NOT NULL,
    toolchain_identity_hash TEXT NOT NULL,
    profile                 TEXT NOT NULL,
    opt                     TEXT NOT NULL,
    flags_json              TEXT NOT NULL,
    outcome                 TEXT NOT NULL,
    obj_sha256              TEXT,
    masked_coff_sha256      TEXT,
    diagnostic_codes_json   TEXT,
    basis_hash              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grid_compile_receipt_tu ON grid_compile_receipt(tu_sha256, toolchain_identity_hash);
"""


@view_hook(CompileAttempt.name)
def apply_compile_receipt(kind: str, result: TaskResult, objects: ObjectStore, con) -> int:
    """Record the verified compile receipt (design §2.4: compile receipts are a view table)."""
    ref = result.outputs.get("receipt")
    if ref is None or not objects.exists(ref) or result.status != ResultStatus.OK:
        return 0
    r = get_json(objects, ref)
    ensure_tables(con, COMPILE_RECEIPT_SQL)
    con.execute(
        "INSERT OR REPLACE INTO grid_compile_receipt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.task_id, str(r.get("tu_sha256", "")), str(r.get("toolchain_identity_hash", "")),
            str(r.get("profile", "default")), str(r.get("opt", "")), _json(r.get("flags", [])),
            str(r.get("outcome", "")), r.get("obj_sha256"), r.get("masked_coff_sha256"),
            _json(r.get("diagnostic_codes")) if r.get("diagnostic_codes") is not None else None,
            str(r.get("basis_hash", result.basis_hash)),
        ),
    )
    return 1


def _json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "CAPABILITY_PREFIX", "CompileAttempt", "FORBIDDEN_FLAGS", "RECEIPT_SCHEMA", "TOOLCHAINS", "ToolchainRoot",
    "default_compile_script", "diagnostic_codes", "masked_coff_sha256", "register_toolchain",
    "resolve_toolchain", "toolchain_identity",
]
