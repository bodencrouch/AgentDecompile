"""Authoritative corpus pipeline contract.

This file is the code form of the operator contract. Dashboard labels and old
JSON snapshots are not sources of truth. Receipts written by a run of this
pipeline, plus the corpus file and any `.mission/queue.md` the operator keeps,
are.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "agentdecompile.corpus-pipeline.v1"

# Two different "cross-match" jobs. Mixing them copies trash.
#
#   identify          — which function is which (names, features, STABS).
#                       Safe before any C exists.
#   apply-cross-build — copy compiling real C onto bound functions.
#                       Only after recover-source. Never copy a body that failed
#                       helpers unless an LLM cleanup of *that* Ghidra C
#                       later compiles.
#
# Operator path: extract → logical_id → calibrate-global → assembly floor →
# compiling Ghidra C → cross-place → leftover AI → objdiff last.
@dataclass(frozen=True)
class PipelineStage:
    token: str
    action_id: str
    label: str
    aliases: tuple[str, ...] = ()
    needs_project: bool = False
    mutating: bool = False


PIPELINE_STAGE_METADATA = (
    PipelineStage("extract", "corpus.extract-stabs", "Extract", needs_project=True),
    PipelineStage("identify", "corpus.match-pair", "Match", aliases=("merge-knowledge",), needs_project=True, mutating=True),
    PipelineStage("calibrate-global", "corpus.calibrate-global", "Calibrate global", mutating=True),
    PipelineStage("assembly-floor", "corpus.workspace", "Link floor", aliases=("generate-projects",), mutating=True),
    PipelineStage("recover-source", "corpus.ghidra-bulk", "Ghidra bulk", aliases=("compile", "preparse"), mutating=True),
    PipelineStage("apply-cross-build", "corpus.cross-place", "Cross-place"),
    PipelineStage("leftover-recover", "corpus.genproject", "Leftover", aliases=("llm-cleanup",)),
    PipelineStage("verify-byte-accuracy", "corpus.objdiff-check", "Objdiff audit", mutating=True),
)

PIPELINE_STAGES = tuple(stage.token for stage in PIPELINE_STAGE_METADATA)

# One release of old --stop-after tokens. compile means Ghidra C compiled,
# not the assembly-floor link.
STAGE_ALIASES = {alias: stage.token for stage in PIPELINE_STAGE_METADATA for alias in stage.aliases}
PIPELINE_STAGE_ACTIONS = {stage.token: stage.action_id for stage in PIPELINE_STAGE_METADATA}


def pipeline_stage_presentation() -> tuple[dict[str, object], ...]:
    """Serialize immutable stage presentation for dashboard adapters."""
    return tuple(
        {
            "token": stage.token,
            "actionId": stage.action_id,
            "label": f"{index} {stage.label}",
            "needsProject": stage.needs_project,
            "mutating": stage.mutating,
        }
        for index, stage in enumerate(PIPELINE_STAGE_METADATA, 1)
    )

# Operator priority. A complete linked executable is first even though
# verify-byte-accuracy is last in the stage list.
PRIORITIES = (
    "compile-complete-executable",
    "cross-match",
    "byte-accuracy",
    "call-graphs-docs-ui",
)

CLAIM_BOUNDARY = (
    "A stage is complete only when that run wrote a receipt whose files exist "
    "on disk. Dashboard text, Atlas tiles, and leftover work-dir files from "
    "an earlier run are not completion. Real C and byte-accuracy are separate "
    "properties. Machine-code wrappers are not recovered source. A compile "
    "is not byte-exact."
)

# Legacy standalone ports. The live pages are on the MCP HTTP server
# (default 8080) at /dashboard, /atlas, and /report.
DEFAULT_DASHBOARD_PORT = 8791
DEFAULT_ATLAS_PORT = 5173
DEFAULT_REPORT_PORT = 3000
DEFAULT_MCP_PAGE_PORT = 8080

# Rail verb vs in-process corpus.run for recover-source.
RECOVER_SOURCE_SPLIT = (
    "On the rail, recover-source is corpus.ghidra-bulk after assembly-floor. "
    "On corpus.run it is the in-process snapshot-C receipt. corpus.run does "
    "not subprocess ghidra-bulk."
)


def resolve_stage(name: str) -> str:
    """Map a live stage name or a one-release alias onto PIPELINE_STAGES."""
    if name in PIPELINE_STAGES:
        return name
    aliased = STAGE_ALIASES.get(name)
    if aliased:
        return aliased
    raise ValueError(
        f"unknown corpus stage {name!r}; valid: {PIPELINE_STAGES} "
        f"aliases: {STAGE_ALIASES}"
    ) from None


def stage_index(name: str) -> int:
    try:
        return PIPELINE_STAGES.index(resolve_stage(name))
    except ValueError as exc:
        raise ValueError(
            f"unknown corpus stage {name!r}; valid: {PIPELINE_STAGES} "
            f"aliases: {STAGE_ALIASES}"
        ) from exc


def stages_through(stop_after: str | None) -> tuple[str, ...]:
    if not stop_after:
        return PIPELINE_STAGES
    return PIPELINE_STAGES[: stage_index(stop_after) + 1]


def stages_catalog() -> dict[str, object]:
    """JSON for `corpus.stages`: live names, aliases, and the recover-source split."""
    return {
        "stages": PIPELINE_STAGES,
        "aliases": dict(STAGE_ALIASES),
        "priorities": PRIORITIES,
        "recoverSource": {
            "rail": "corpus.ghidra-bulk after assembly-floor",
            "corpusRun": "in-process snapshot-C receipt; does not subprocess ghidra-bulk",
        },
        "claimBoundary": CLAIM_BOUNDARY,
    }
