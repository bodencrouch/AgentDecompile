"""Admission declarations for corpus verbs.

One ``VerbAdmission`` per verb says what the dashboard's admission loop needs
to know before it runs the verb: whether it writes the store, what it holds,
what happens to it on pause, and which lane it queues in.  The CLI declares
them next to each parser through ``_declare``; the catalogue copies them onto
the action row; the job runner reads them at the acceptance point.

Register H5: a verb the loop cannot see is a verb it cannot drain.  A verb
with no declaration therefore resolves to ``UNDECLARED``, the conservative
default (mutating, database scope, long-running, drains on pause), never to a
read-only one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

IdentityScope = Literal["", "database", "pair"]
Snapshot = Literal["none", "temp-copy", "private-snapshot"]
OutputScope = Literal["none", "output-tree", "receipts-dir"]
BudgetClass = Literal["micro", "small", "medium", "large", "unbounded"]
Cancel = Literal["sigterm", "cooperative", "never"]

UNDECLARED_LANE = "undeclared"


@dataclass(frozen=True)
class VerbAdmission:
    """What the admission loop may assume about one verb.

    ``mutating``       writes the store or another shared corpus artefact.
    ``long_running``   minutes, not seconds; the dock shows a progress row.
    ``identity_scope`` which lock it holds: the store (``database``), one
                       directed pair (``pair``), or nothing.
    ``read_only``      never writes the store.  Implies ``mutating=False``
                       and no identity scope.
    ``snapshot``       reads a copy rather than the live store.  Only a
                       snapshot read is licensed to skip the identity lock;
                       a read-only verb on the live store still waits.
    ``output_scope``   where its writes land outside the store.  Exporters
                       take an output-tree lock keyed by the out path.
    ``drains_on_pause`` a paused scope lets it finish rather than signal it.
    ``boots_analyzer`` starts the analyzer; counted against memory-aware
                       admission.
    ``lane``           queue it competes in; lanes get per-lane quotas.
    ``budget_class``   expected cost; a slot for cost-aware policies.
    ``cancel``         how it is stopped when a pause does not drain it.
    ``declared``       False when the row is the conservative default, not a
                       declaration made by the verb.
    """

    mutating: bool
    long_running: bool
    identity_scope: IdentityScope
    read_only: bool
    snapshot: Snapshot
    output_scope: OutputScope
    drains_on_pause: bool
    boots_analyzer: bool
    lane: str
    budget_class: BudgetClass
    cancel: Cancel
    declared: bool = True

    def __post_init__(self) -> None:
        if self.read_only and (self.mutating or self.identity_scope):
            raise ValueError(
                "a read_only verb cannot be mutating or hold an identity scope"
            )
        if not self.lane:
            raise ValueError("a verb needs a lane")

    @property
    def skips_identity_lock(self) -> bool:
        """H5 (3a): a snapshot read never takes or waits on the identity lock.

        ``snapshot != "none"`` is what licenses this; a read-only verb that
        opens the live store would see a torn read if it skipped the lock.
        """
        return self.read_only and self.snapshot != "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# The conservative default.  Named so a reader of the catalogue can tell a
# declaration from an absence of one.  Mutating, database-scoped and
# long-running: the loop drains it on pause and never treats it as read-only.
UNDECLARED = VerbAdmission(
    mutating=True,
    long_running=True,
    identity_scope="database",
    read_only=False,
    snapshot="none",
    output_scope="none",
    drains_on_pause=True,
    boots_analyzer=False,
    lane=UNDECLARED_LANE,
    budget_class="unbounded",
    cancel="sigterm",
    declared=False,
)

# verb name -> declaration.  Filled by the CLI's ``_declare`` when the parser
# is built; ``admission_for`` builds the parser on first use so the registry
# is never read empty.
VERB_ADMISSIONS: dict[str, VerbAdmission] = {}


def declare(verb: str, admission: VerbAdmission, *aliases: str) -> VerbAdmission:
    """Record *admission* for *verb* and each alias.  Returns the declaration."""
    for name in (verb, *aliases):
        VERB_ADMISSIONS[name] = admission
    return admission


def from_legacy(*, mutating: bool, long_running: bool, identity_scope: str) -> VerbAdmission:
    """The default for a verb that only set the three legacy parser attributes.

    The three fields the parser stated win; everything the parser did not
    state stays at the conservative default, so the row is never read-only
    and always drains on pause.
    """
    scope: IdentityScope = identity_scope if identity_scope in ("database", "pair") else ""
    return replace(
        UNDECLARED,
        mutating=bool(mutating),
        long_running=bool(long_running),
        identity_scope=scope,
    )


def _ensure_registry() -> None:
    if VERB_ADMISSIONS:
        return
    # Local import: the CLI imports this module at load time.
    from agentdecompile_recovery.corpus.cli import build_parser

    build_parser()


def admission_for(verb: str) -> VerbAdmission:
    """The declaration for *verb*, or ``UNDECLARED`` when it made none."""
    _ensure_registry()
    return VERB_ADMISSIONS.get(verb, UNDECLARED)


def describe() -> list[dict[str, Any]]:
    """Every declaration as a sorted, JSON-able table."""
    _ensure_registry()
    return [
        {"verb": verb, **VERB_ADMISSIONS[verb].to_dict()}
        for verb in sorted(VERB_ADMISSIONS)
    ]
