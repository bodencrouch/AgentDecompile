"""``parity-check``: the object-diff check of one candidate object against its target (§3.4).

Inputs: ``target`` (the pinned target ``.o`` from ``mkobj-target``) and ``candidate`` (a COFF
object, normally a verified ``compile-attempt`` output).  Params: ``symbol`` (optional),
``verifier_id`` -- ``parity:<sha256>`` for the native checker binary or ``parity-wasm:<sha256>``
for the node + wasm bundle -- and ``timeout_s``.  Capability: the ``verifier_id`` itself, so a
node with a different checker build advertises a different capability and is never offered a
task keyed to the pinned one (U125).

Sides are **named**: the native CLI is rendered ``-1 <target> -2 <candidate>`` and the node
helper ``<candidate as base> <target>``, so the reversed-order call at seed_validation.py:353-357
cannot recur.  Output: ``receipt`` -- the ``agentdecompile.verify-objdiff.v1`` report parsed
fail-closed by ``objdiff_verification.parse_objdiff_report`` (empty output is never a match),
with the raw checker text spilled to its own ``raw`` object and ``grade`` = ``matched`` |
``mismatched`` | ``error``.  Budget SMALL (MEASURED 0.06 s native floor, 0.5-1.2 s node).
The bare ``subprocess.run`` of objdiff_check.py:42 gets the deadline it lacks.

``verify``: recompute the receipt and compare content addresses (1:1, so a parity receipt from an
unverified key is a priority hint; independent verifier keys make it load-bearing).

Acceptance tests (named, landed with U136):

* ``test_parity_task_id_same_for_native_and_wasm_pinned_ids``;
* ``test_parity_receipt_byte_identical_same_verifier`` -- two runs, one ``receipt`` ref;
* ``test_parity_stub_never_returns_yields_timeout_within_budget``;
* ``test_parity_sides_named`` -- swapping inputs changes ``sides`` and the task id;
* ``test_parity_empty_output_fails_closed``;
* ``test_parity_checker_missing_refuses_by_name``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    ObjectStore,
    Refused,
    Registry,
    ResultStatus,
    TaskResult,
    TaskSpec,
    Verification,
    digest,
    task_kind,
)
from agentdecompile_grid.view.applier import ensure_tables, view_hook

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
    verify_by_recompute,
)

RECEIPT_SCHEMA = "agentdecompile.verify-objdiff.v1"
NATIVE_PREFIX = "parity:"
WASM_PREFIX = "parity-wasm:"
_ROWS = re.compile(r"rows identical:\s*(\d+),\s*differing:\s*(\d+)")
_RESULT = re.compile(r"RESULT:\s*(MATCH 100%|MISMATCH \(([0-9.]+)%\))")


# --------------------------------------------------------------------------- checkers
@dataclasses.dataclass(frozen=True)
class ParityChecker:
    verifier_id: str
    flavour: str                 # "native" | "node"
    path: Path                   # native binary, or the node script
    node: Path | None = None
    wasm_root: Path | None = None

    def argv(self, target: Path, candidate: Path, symbol: str) -> list[str]:
        if self.flavour == "native":
            return [str(self.path), "diff", "-1", str(target), "-2", str(candidate), "-o", "-", "--format", "json-pretty"]
        argv = [str(self.node), str(self.path), str(candidate), str(target)]
        if symbol:
            argv.append(symbol)
        return argv

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.flavour == "node" and self.wasm_root is not None:
            env["AGENT_DECOMPILE_OBJDIFF_WASM_ROOT"] = str(self.wasm_root)
        return env


PARITY_CHECKERS = Registry("parity checker")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register_native(path: str | Path, *, replace: bool = True) -> ParityChecker:
    """Register the native checker binary; its id is ``parity:<sha256 of the binary>``."""
    binary = Path(path).expanduser().resolve()
    if not binary.is_file():
        raise Refused("parity-checker-missing:native")
    checker = ParityChecker(verifier_id=NATIVE_PREFIX + _file_sha256(binary), flavour="native", path=binary)
    PARITY_CHECKERS.register(checker.verifier_id, checker, replace=replace)
    return checker


def register_node(script: str | Path, wasm_root: str | Path, *, node: str | None = None, replace: bool = True) -> ParityChecker:
    """Register the node helper + wasm bundle; id = ``parity-wasm:<sha256 over script, js, wasm>``."""
    script_path = Path(script).expanduser().resolve()
    root = Path(wasm_root).expanduser().resolve()
    node_path = Path(node or shutil.which("node") or "")
    if not script_path.is_file() or not node_path.is_file():
        raise Refused("parity-checker-missing:node")
    dist = root / "node_modules" / "objdiff-wasm" / "dist"
    parts = [_file_sha256(script_path)]
    for name in ("objdiff.js", "objdiff.core.wasm"):
        candidate = dist / name
        if not candidate.is_file():
            raise Refused(f"parity-checker-missing:wasm:{name}")
        parts.append(_file_sha256(candidate))
    checker = ParityChecker(
        verifier_id=WASM_PREFIX + digest("\n".join(parts).encode()), flavour="node",
        path=script_path, node=node_path, wasm_root=root,
    )
    PARITY_CHECKERS.register(checker.verifier_id, checker, replace=replace)
    return checker


def discover_checkers() -> list[ParityChecker]:
    """Register whatever this host has (env / PATH); used when no canary ran."""
    found: list[ParityChecker] = []
    native = os.environ.get("AGENT_DECOMPILE_OBJDIFF", "").strip() or shutil.which("objdiff")
    if native:
        try:
            found.append(register_native(native))
        except Refused:
            pass
    from ..corpus.objdiff_check import default_script

    script = default_script()
    wasm_root = os.environ.get("AGENT_DECOMPILE_OBJDIFF_WASM_ROOT", "").strip() or os.environ.get("MIZUCHI_ROOT", "").strip()
    if script is not None and wasm_root:
        try:
            found.append(register_node(script, wasm_root))
        except Refused:
            pass
    return found


def resolve_checker(verifier_id: str) -> ParityChecker:
    if verifier_id in PARITY_CHECKERS:
        return PARITY_CHECKERS.get(verifier_id)
    for checker in discover_checkers():
        if checker.verifier_id == verifier_id:
            return checker
    raise Refused(f"parity-checker-not-present:{verifier_id[:24]}")


# --------------------------------------------------------------------------- node text parsing
def parse_node_report(returncode: int, output: str) -> dict[str, Any]:
    """The node helper's text into the ``verify-objdiff.v1`` shape, fail-closed like the parser."""
    text = output if isinstance(output, str) else ""
    rows = _ROWS.search(text)
    result = _RESULT.search(text)
    if not text.strip() or rows is None or result is None or returncode not in (0, 1):
        return {
            "schema": RECEIPT_SCHEMA, "status": "error", "differences": -1,
            "message": "node checker produced no verdict" if text.strip() else "node checker produced empty output",
            "objdiffExit": returncode, "detailLevel": "row",
        }
    differing = int(rows.group(2))
    matched = returncode == 0 and differing == 0 and result.group(1) == "MATCH 100%"
    return {
        "schema": RECEIPT_SCHEMA, "status": "matched" if matched else "mismatched",
        "differences": 0 if matched else max(differing, 1), "message": "Object files match" if matched else "Object files do not match",
        "objdiffExit": returncode, "detailLevel": "row", "rowsIdentical": int(rows.group(1)), "rowsDiffering": differing,
        "matchPercent": 100.0 if matched else float(result.group(2) or 0.0),
    }


# --------------------------------------------------------------------------- the kind
@task_kind
class ParityCheck(PlannableKind):
    name = "parity-check"
    version = 1
    budget = BudgetClass.SMALL
    capabilities = ("parity:<hash> | parity-wasm:<hash>",)   # template; the spec carries verifier_id
    INPUTS: Mapping[str, str] = {"target": "pinned target object (.o from mkobj-target)", "candidate": "candidate COFF object"}
    PARAMS_SCHEMA: Mapping[str, str] = {
        "verifier_id": "parity:<sha256 of native binary> or parity-wasm:<sha256 of script+js+wasm>",
        "symbol": "optional function symbol to compare",
        "timeout_s": "optional kill deadline; capped at SMALL (60 s)",
    }
    OUTPUTS: Mapping[str, str] = {
        "receipt": "verify-objdiff.v1 report (fail-closed), sides named, grade = status",
        "raw": "raw checker stdout (never parsed from stderr)",
    }

    @staticmethod
    def required_capabilities(spec: TaskSpec) -> tuple[str, ...]:
        return (str(spec.params.get("verifier_id", "")),)

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        verifier_id = str(require_param(spec, "verifier_id", kind=self.name))
        if not (verifier_id.startswith(NATIVE_PREFIX) or verifier_id.startswith(WASM_PREFIX)):
            raise Refused(f"verifier-id-malformed:{verifier_id[:24]}")
        checker = resolve_checker(verifier_id)                     # refusal first
        target_ref = require_input(spec, "target", kind=self.name)
        candidate_ref = require_input(spec, "candidate", kind=self.name)
        symbol = str(spec.params.get("symbol") or "")
        deadline = deadline_for(self.budget, spec.params.get("timeout_s"))
        started = time.monotonic()
        scratch_dir = Path(scratch)
        target = materialize_object(objects, target_ref, scratch_dir / "target.o")
        candidate = materialize_object(objects, candidate_ref, scratch_dir / "candidate.obj")
        outcome = run_argv(checker.argv(target, candidate, symbol), cwd=scratch_dir, timeout_s=deadline, env=checker.env())
        if outcome.timed_out:
            raise Infra(f"timeout:parity-check:{int(deadline)}s")
        if checker.flavour == "native":
            from ..objdiff_verification import parse_objdiff_report

            report = parse_objdiff_report(outcome.returncode, outcome.stdout)
        else:
            report = parse_node_report(outcome.returncode, outcome.stdout)
        raw_ref = objects.put(outcome.stdout.encode("utf-8", "replace"))
        receipt = {k: v for k, v in report.items() if k != "output"}
        receipt.update({
            "kind": self.name, "kind_version": self.version, "verifier_id": verifier_id, "verifier": checker.flavour,
            "sides": {"target": target_ref.hex, "candidate": candidate_ref.hex}, "symbol": symbol,
            "grade": str(report.get("status", "error")), "basis_hash": spec.basis_hash,
        })
        if "message" in receipt:
            receipt["message"] = scrub_paths(str(receipt["message"]))
        assert_portable(receipt)
        outputs = {"receipt": put_json(objects, receipt), "raw": raw_ref}
        return make_result(
            spec, outputs, elapsed_s=time.monotonic() - started,
            metrics={"checker_wall_s": round(outcome.elapsed_s, 3), "deadline_s": deadline, "stderr_sha256": outcome.stderr_sha256},
        )

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        return verify_by_recompute(self, spec, result, objects, scratch, compare=("receipt",), method="parity")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "budget": cls.budget.value, "capabilities": list(cls.capabilities),
            "inputs": dict(cls.INPUTS), "params": dict(cls.PARAMS_SCHEMA), "outputs": dict(cls.OUTPUTS),
            "verify": "recompute the receipt (1:1): a hint from any key, load-bearing from independent verifier keys",
            "checkers_registered": PARITY_CHECKERS.names(), "status": "working",
            "sides": {"native": "-1 <target> -2 <candidate>", "node": "<candidate as base> <target> [symbol]"},
        }


# --------------------------------------------------------------------------- view hook
PARITY_RECEIPT_SQL = """
CREATE TABLE IF NOT EXISTS grid_parity_receipt (
    task_id          TEXT PRIMARY KEY,
    target_sha256    TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    verifier_id      TEXT NOT NULL,
    grade            TEXT NOT NULL,
    differences      INTEGER NOT NULL,
    basis_hash       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grid_parity_candidate ON grid_parity_receipt(candidate_sha256);
"""


@view_hook(ParityCheck.name)
def apply_parity_receipt(kind: str, result: TaskResult, objects: ObjectStore, con) -> int:
    ref = result.outputs.get("receipt")
    if ref is None or not objects.exists(ref) or result.status != ResultStatus.OK:
        return 0
    r = get_json(objects, ref)
    sides = r.get("sides") or {}
    ensure_tables(con, PARITY_RECEIPT_SQL)
    con.execute(
        "INSERT OR REPLACE INTO grid_parity_receipt VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.task_id, str(sides.get("target", "")), str(sides.get("candidate", "")), str(r.get("symbol", "")),
            str(r.get("verifier_id", "")), str(r.get("grade", "error")), int(r.get("differences", -1)),
            str(r.get("basis_hash", result.basis_hash)),
        ),
    )
    return 1


__all__ = [
    "NATIVE_PREFIX", "PARITY_CHECKERS", "ParityCheck", "ParityChecker", "RECEIPT_SCHEMA", "WASM_PREFIX",
    "discover_checkers", "parse_node_report", "register_native", "register_node", "resolve_checker",
]
