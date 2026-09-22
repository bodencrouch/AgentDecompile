"""Declared analyzer lanes: ``analysis-slice``, ``decompile-chunk``, ``bsim-sigs`` (design §3.1, §3.2, §3.7).

These kinds carry their §3 parameter schema, budget class and capability so the registry,
``describe`` and the planner know them, and refuse by name until the analyzer-side adapters land
(U137 headless slices with a per-file analysis timeout, U139 decompile chunks with program
affinity, U141 signature ranges with a pinned template).  Every ``run`` raises ``NotConfigured``
naming the analyzer capability ``analyzer:<version>:<options_hash>`` the node would have to
prove by canary (open a fixture packed program headless; inventory hash must equal the pinned
value).  Packed programs are image-bearing (``restricted``): fleet and operator keys only (§6.3).

Acceptance tests (named, landed with U137/U139/U141):

* ``test_analysis_kinds_declared`` -- each kind describes itself and ``run`` raises
  ``NotConfigured`` naming ``analyzer:<version>:<options_hash>``;
* ``test_analysis_slice_checkpoint_is_packed_program`` (U137 A2.1/A2.3);
* ``test_decompile_chunk_partial_plus_continuation_equals_full`` (U139);
* ``test_bsim_sigs_without_template_refused`` (U141).
"""
from __future__ import annotations

from typing import Any, Mapping

from agentdecompile_grid.core import (
    BudgetClass,
    NotConfigured,
    ObjectStore,
    TaskResult,
    TaskSpec,
    Verification,
    task_kind,
)

from ._common import PlannableKind, check_kind

ANALYZER_CAPABILITY = "analyzer:<version>:<options_hash>"


def analyzer_capability(spec: TaskSpec) -> str:
    version = str(spec.params.get("analyzer_version") or "<version>")
    options = str(spec.params.get("options_hash") or "<options_hash>")
    return f"analyzer:{version}:{options}"


class DeclaredAnalyzerKind(PlannableKind):
    """Base for a declared (not yet runnable) analyzer-side kind."""

    name = ""
    version = 1
    budget = BudgetClass.MEDIUM
    capabilities = (ANALYZER_CAPABILITY,)
    INPUTS: Mapping[str, str] = {}
    PARAMS_SCHEMA: Mapping[str, str] = {}
    OUTPUTS: Mapping[str, str] = {}
    OUTPUT_ROLES: Mapping[str, str] = {"packed_program": "restricted", "fragment": "restricted"}   # image-bearing (§6.3)
    UNIT = ""
    INPUT_ROLE = "restricted"

    @classmethod
    def required_capabilities(cls, spec: TaskSpec) -> tuple[str, ...]:
        caps = [analyzer_capability(spec)]
        if "packed_program" in spec.inputs:
            caps.append(f"program:{spec.inputs['packed_program'].hex}")
        return tuple(caps)

    def run(self, spec: TaskSpec, objects: ObjectStore, scratch: str) -> TaskResult:
        check_kind(spec, self.name, self.version)
        raise NotConfigured(
            f"{self.name}: analyzer lane not present in this checkout yet ({self.UNIT}); a node must prove "
            f"{analyzer_capability(spec)} by canary before it can be offered this kind"
        )

    def verify(self, spec: TaskSpec, result: TaskResult, objects: ObjectStore, scratch: str) -> Verification:
        raise NotConfigured(f"{self.name}: analyzer lane not present in this checkout yet ({self.UNIT})")

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "kind": cls.name, "version": cls.version, "budget": cls.budget.value, "capabilities": list(cls.capabilities),
            "inputs": dict(cls.INPUTS), "input_role": cls.INPUT_ROLE, "params": dict(cls.PARAMS_SCHEMA),
            "outputs": dict(cls.OUTPUTS), "output_roles": {k: cls.OUTPUT_ROLES.get(k, "public") for k in cls.OUTPUTS},
            "status": "declared", "unit": cls.UNIT, "roles": ["fleet", "operator"],
        }


@task_kind
class AnalysisSlice(DeclaredAnalyzerKind):
    name = "analysis-slice"
    budget = BudgetClass.LARGE      # chunk-large / fleet: 180-300 s per slice incl. JVM start, open, save, pack
    UNIT = "U137"
    INPUTS = {"packed_program": "gzf_k: the packed program after slice k (checkpoint)"}
    PARAMS_SCHEMA = {
        "analyzer_version": "pinned analyzer version", "options_hash": "pinned analysis option set",
        "slice_budget_s": "per-file analysis timeout for this slice", "k": "slice index",
        "timeout_policy": "{per_slice, total} recorded in the basis (U65)",
        "pin_policy": "two-key-agree | operator-lexmin (basis field, §5.3)",
    }
    OUTPUTS = {"packed_program": "gzf_{k+1}", "receipt": "{analysis_idle: bool, elapsed, phase}"}


@task_kind
class DecompileChunk(DeclaredAnalyzerKind):
    name = "decompile-chunk"
    budget = BudgetClass.MEDIUM     # chunk: 1-32 s typical, 320 s worst (16 x 20 s cap)
    UNIT = "U139"
    INPUTS = {"packed_program": "pinned gzf", "entries": "shard entry list object (16 entries by default)"}
    PARAMS_SCHEMA = {
        "analyzer_version": "pinned analyzer version", "options_hash": "pinned decompiler options (grabFromProgram + fixed toggles)",
        "timeout_policy": "{per_function_s: 20, task_wall_s: 300}", "chunk": "chunk index",
    }
    OUTPUTS = {
        "rows": "canonical JSONL {entry, name, size, prototype, calling_convention, decompiled_c|null, error|null, timed_out, elapsed_ms}",
        "receipt": "chunk receipt; on SIGTERM the covered subset is flushed and a continuation task names the rest",
    }


@task_kind
class BsimSigs(DeclaredAnalyzerKind):
    name = "bsim-sigs"
    budget = BudgetClass.MEDIUM     # micro per range in the design; MEDIUM here covers the per-node open (10-30 s)
    UNIT = "U141"
    INPUTS = {"packed_program": "pinned gzf"}
    PARAMS_SCHEMA = {
        "analyzer_version": "pinned analyzer version", "options_hash": "pinned option set",
        "entry_cursor": "first entry of the range", "n": "range size (default 128)",
        "template_id": "pinned signature template (mandatory; live server state is not a basis)",
        "generator_revision": "signature generator revision (pending basis field, determinism_basis.py:62-69)",
    }
    OUTPUTS = {"fragment": "signature XML fragment for the range", "receipt": "range receipt"}


ANALYSIS_KINDS = (AnalysisSlice, DecompileChunk, BsimSigs)

__all__ = ["ANALYSIS_KINDS", "ANALYZER_CAPABILITY", "AnalysisSlice", "BsimSigs", "DecompileChunk", "analyzer_capability"]
