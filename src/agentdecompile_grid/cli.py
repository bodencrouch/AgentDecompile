"""``adgrid`` -- the one command every node runs (design §1.3, §8 U120/U125/U128/U129).

Thin dispatch over the registries in ``core``: every verb resolves adapters by name and never
holds pipeline state.  The grid never imports the recovery package; lane modules (the
pipeline's task kinds) are loaded **by name** from, in order, ``GridConfig.lanes``, the
``ADGRID_LANES`` environment variable (``os.pathsep``- or comma-separated module names) and the
``agentdecompile_grid.lanes`` entry-point group.  ``publish`` reaches a lane's planner through
``TASK_KINDS.get(kind).plan(...)`` (duck-typed), never through a literal import.  The builtin
kinds (``agentdecompile_grid.tasks``, plus the ``agentdecompile_grid.task_kinds`` entry-point
group) are imported at start, so every verb sees them.

Verbs::

    adgrid join [<url>] [--with toolchain <hash> | --toolchain-path DIR] [--with analyzer] [--idle-only] [--cores N]
                (no url: $ADGRID_INVITE)
    adgrid leave | status
    adgrid publish <kind> --snapshot PATH|sha256:... [--basis-hash H] [--shard-size N]
                          [--allow-budget small|medium|large] [--option k=v ...] [--subject S]
    adgrid work [--once] [--kinds a,b] [--node NAME] [--role R]      adgrid verify [--once] [--node NAME] [--role R]
    adgrid view materialize <db> [--partition P ...] [--resume] [--applier sqlite]
    adgrid view status <db>
    adgrid fleet up|down|status|replace --provider NAME --count N --lanes a,b [--role fleet] [--node ID ...]
    adgrid objects put FILE | get REF [--out FILE] | gc
    adgrid log tail <partition> [--since N] [--limit N]
    adgrid describe [--json] [--verbose]

Wiring (the integration contract):

* ``GridConfig.load()`` is the one configuration entry; ``--root`` / ``$ADGRID_ROOT`` re-root it.
* stores come from ``transport.local.LocalTransport.from_config`` (``adapters.*``); the layout is
  ``config.PathsConfig``: object store at ``<root>/objects``, log at ``<root>/log``, heads at
  ``<root>/heads``, node state at ``<root>/nodes/<name>``.
* the frontier is ``log.frontier.derive`` everywhere (``publish``, ``work``, ``verify``).
* records are appended through ``log.outbox.Appender`` (``publish`` directly, the loops through
  the node outbox's ``RecordWriter``); the producer/verifier identity *is* the record signer.
* ``work``/``verify`` run as a node identity under ``<root>/nodes/<name>``: the one ``join`` bound,
  or a self-rooted key whose capabilities the canaries prove.  A verifier needs a second key
  with disjoint lineage (design §2.5), so ``verify`` defaults to ``verifier.node_name`` /
  ``verifier.role``.

Errors: every failure is a ``GridError`` subclass printed as ``error: <Class>: <message>`` with
the class's exit code -- never a traceback (``ADGRID_DEBUG=1`` re-raises for development).
Unexpected exceptions are reported by type only.  Messages never carry a plaintext slug (lanes
hash them) and absolute paths are scrubbed at the edge.

Attach-first (user rule: exclusive lock is not join): ``join``/``leave``/``status`` delegate to
``worker.agent``, which attaches to a running local agent before it would ever start one, and
reports ``EADDRINUSE`` as ``AlreadyOwned`` (exit 3), never as a retry.

Acceptance tests (named, landed in the verification phase):

* ``test_cli_no_recovery_import`` -- a grep for the recovery package's name under the grid package is empty;
* ``test_cli_every_error_is_named_and_coded`` -- no traceback on any refusal; exit codes match;
* ``test_cli_publish_derives_basis_from_snapshot`` and ``test_cli_publish_refuses_foreign_basis``;
* ``test_cli_publish_is_idempotent`` -- a second publish of the same snapshot publishes nothing;
* ``test_cli_describe_lists_every_registry`` (with and without lanes loaded);
* ``test_cli_view_materialize_twice_identical_dump``;
* ``test_cli_join_attaches_never_starts`` (U125);
* ``test_cli_grid_of_one`` -- publish, work --once, verify --once (second identity), view materialize.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import __version__
from .core import (
    APPLIERS,
    CANARIES,
    HEAD_STORES,
    LOG_STORES,
    OBJECT_STORES,
    PROVIDERS,
    SIGNERS,
    TASK_KINDS,
    TRANSPORTS,
    VERIFIERS,
    BudgetClass,
    GridError,
    NotConfigured,
    ObjectRef,
    RecordType,
    Refused,
    TaskSpec,
    check_basis_projection,
)

LANES_ENV = "ADGRID_LANES"
ROOT_ENV = "ADGRID_ROOT"
INVITE_ENV = "ADGRID_INVITE"
LANES_ENTRY_POINT_GROUP = "agentdecompile_grid.lanes"
BUILTIN_KIND_MODULE = "agentdecompile_grid.tasks"

_ABS_POSIX = re.compile(r"(?<![\w./])/(?:[^/\s'\"()]+/)+[^/\s'\"()]*")
_ABS_WIN = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"()]*")


# --------------------------------------------------------------------------- errors
class Unexpected(GridError):
    """A non-grid exception reached the edge; reported by type, never as a traceback."""

    exit_code = 1


class LaneImportFailed(GridError):
    """A configured lane module could not be imported; names the module and the exception type."""

    exit_code = 9


class HeadConflict(GridError):
    """A head CAS lost against a concurrent writer; the outbox retries, the CLI names it."""

    exit_code = 14


class NoSuchKind(GridError):
    exit_code = 15


class UsageError(GridError):
    exit_code = 2


def scrub(text: str) -> str:
    return _ABS_POSIX.sub("<path>", _ABS_WIN.sub("<path>", text))


# --------------------------------------------------------------------------- configuration and stores
def _import(module: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise NotConfigured(f"{module} not present in this checkout yet") from exc


def load_config(root: str | None = None):
    """``GridConfig.load()`` re-rooted at ``--root`` / ``$ADGRID_ROOT`` when given (``$ADGRID_HOME`` is the config's own)."""
    cfg = _import("agentdecompile_grid.config").GridConfig.load()
    explicit = root or os.environ.get(ROOT_ENV, "").strip()
    return cfg.with_root(Path(explicit).expanduser()) if explicit else cfg


@dataclass
class Grid:
    """What every store-touching verb needs: the rooted config, the transport and the operator signer."""

    cfg: Any
    transport: Any

    @classmethod
    def open(cls, args: argparse.Namespace) -> "Grid":
        cfg = load_config(getattr(args, "root", None))
        transport = _import("agentdecompile_grid.transport.local").LocalTransport.from_config(cfg)
        return cls(cfg, transport)

    @property
    def root(self) -> Path:
        return Path(self.cfg.root)

    def objects(self):
        return self.transport.objects()

    def log(self):
        return self.transport.log()

    def heads(self):
        return self.transport.heads()

    def signer(self):
        """The operator signer (``adapters.signer`` / ``signing.*``): ``null`` on a laptop grid."""
        return _import("agentdecompile_grid.log.signing").signer_from_config(self.cfg.signing_locator())

    def frontier_policy(self):
        return _import("agentdecompile_grid.log.frontier").FrontierPolicy.from_config(self.cfg.to_mapping("frontier"))

    def record_filters(self):
        """The frontier's filter chain (U126): revoked keys (``policy/revoked``) and the per-key seq-window rate limit (``limits.*``)."""
        frontier = _import("agentdecompile_grid.log.frontier")
        keys = _import("agentdecompile_grid.log.keys")
        return frontier.filters_from_config(self.cfg.to_mapping("limits"), revoked=keys.RevocationList.load(self.objects()))

    def keyring(self):
        """A ``log.signing.Keyring`` filled from ``keyring.sources`` (local identities, invite objects, key announces)."""
        return _import("agentdecompile_grid.log.signing").Keyring.from_config(self.cfg.keyring_locator(), log=self.log(), objects=self.objects())

    def derive(self, *, partitions: Sequence[str] | None = None, kinds: Sequence[str] | None = None, now: float | None = None):
        frontier = _import("agentdecompile_grid.log.frontier")
        return frontier.derive(self.log(), self.objects(), time.time() if now is None else now, policy=self.frontier_policy(),
                               partitions=partitions, kinds=kinds, filters=self.record_filters())

    def appender(self, signer=None):
        outbox = _import("agentdecompile_grid.log.outbox")
        backoff = _import("agentdecompile_grid.log.backoff").BackoffPolicy.from_config(self.cfg.to_mapping("backoff"))
        return outbox.Appender(self.log(), self.heads(), signer or self.signer(), backoff=backoff)


# --------------------------------------------------------------------------- lanes and kinds
def lane_module_names(cfg: Any = None) -> list[str]:
    names: list[str] = []
    if cfg is None:
        try:
            cfg = load_config(None)
        except GridError:
            cfg = None
    for name in (getattr(cfg, "lanes", None) or ()) if cfg is not None else ():
        names.append(str(name))
    env = os.environ.get(LANES_ENV, "")
    for chunk in re.split(r"[,%s]" % re.escape(os.pathsep), env):
        if chunk.strip():
            names.append(chunk.strip())
    try:
        from importlib.metadata import entry_points

        for ep in entry_points(group=LANES_ENTRY_POINT_GROUP):
            names.append(ep.value.split(":", 1)[0])
    except Exception:  # metadata unavailable: nothing to add
        pass
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def load_builtin_kinds() -> None:
    """The builtin kinds and the ``agentdecompile_grid.task_kinds`` entry-point group (once per process)."""
    tasks = importlib.import_module(BUILTIN_KIND_MODULE)
    tasks.ensure_discovered()


def load_lanes(cfg: Any = None) -> list[str]:
    """Import every configured lane module (each registers its kinds and view hooks on import)."""
    load_builtin_kinds()
    loaded: list[str] = []
    for name in lane_module_names(cfg):
        try:
            importlib.import_module(name)
        except GridError:
            raise
        except Exception as exc:
            raise LaneImportFailed(f"lane module {name!r}: {type(exc).__name__}") from exc
        loaded.append(name)
    return loaded


def import_modules_for_children(cfg: Any = None) -> tuple[str, ...]:
    """What a sandbox child imports so the kinds exist there too."""
    return (BUILTIN_KIND_MODULE, *lane_module_names(cfg))


# --------------------------------------------------------------------------- output
def emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, indent=2, default=str))
        return
    if isinstance(payload, Mapping):
        for key in sorted(payload):
            value = payload[key]
            if isinstance(value, (Mapping, list, tuple)):
                value = json.dumps(value, sort_keys=True, default=str)
            print(f"{key}: {value}")
    else:
        print(payload)


def parse_options(pairs: Sequence[str] | None) -> dict[str, Any]:
    """``k=v`` pairs; JSON values when they parse, comma lists for ``flags``/``passes``/``verbs``."""
    out: dict[str, Any] = {}
    for pair in pairs or ():
        if "=" not in pair:
            raise UsageError(f"--option expects key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        key = key.strip()
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = [v for v in value.split(",") if v] if key in ("flags", "passes", "verbs") else value
    return out


# --------------------------------------------------------------------------- join / leave / status
def _canary_plan(args: argparse.Namespace) -> tuple[dict[str, Any] | None, list[str] | None, list[str]]:
    """``--with``/``--toolchain-path`` -> (canary pool, canary names to run, lanes asked for)."""
    canaries_mod = _import("agentdecompile_grid.worker.canaries")
    pool: dict[str, Any] = dict(CANARIES.items())
    only = ["python"]
    lanes: list[str] = []
    toolchain_hash = ""
    for entry in args.with_ or ():
        if entry[0] == "toolchain":
            if len(entry) != 2:
                raise UsageError("--with toolchain needs a hash")
            toolchain_hash = entry[1]
            only.append("toolchain")
            lanes.append("toolchain")
        elif entry[0] == "analyzer":
            only.append("analyzer")
            lanes.append("analyzer")
        else:
            raise UsageError(f"unknown --with lane {entry[0]!r} (toolchain <hash> | analyzer)")
    if args.toolchain_path or toolchain_hash:
        pool["toolchain"] = canaries_mod.ToolchainCanary(toolchain_path=args.toolchain_path, identity_hash=toolchain_hash)
        if "toolchain" not in only:
            only.append("toolchain")
    return pool, only, lanes


def cmd_join(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    lanes_loaded = load_lanes(grid.cfg)
    agent = _import("agentdecompile_grid.worker.agent")
    loop_mod = _import("agentdecompile_grid.worker.loop")
    frontier = _import("agentdecompile_grid.log.frontier")
    policy = grid.frontier_policy()
    pool, only, lanes = _canary_plan(args)
    worker_config = loop_mod.WorkerConfig.from_grid_config(grid.cfg, lanes=lanes or None, import_modules=import_modules_for_children(grid.cfg), cores=args.cores)
    result = agent.join(
        args.url or None, state_dir=grid.cfg.node_state_dir(args.node), lanes=lanes, cores=args.cores, idle_only=bool(args.idle_only),
        transport=grid.transport, derive=lambda log, objects, now: frontier.derive(log, objects, now, policy=policy),
        config=worker_config, key_algorithm=grid.cfg.worker.key_algorithm, canaries=pool, canary_only=only,
    )
    emit({"mode": result.mode, "lanes_loaded": lanes_loaded, **dict(result.status)}, as_json=args.json)
    if result.mode == "bootstrapped" and result.agent is not None and not args.no_run:
        result.agent.run()          # blocking driver; Ctrl-C becomes leave
    return 0


def cmd_leave(args: argparse.Namespace) -> int:
    agent = _import("agentdecompile_grid.worker.agent")
    result = agent.leave()
    emit({"mode": result.mode, **dict(result.status)}, as_json=args.json)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    agent = _import("agentdecompile_grid.worker.agent")
    emit(agent.status(), as_json=args.json)
    return 0


# --------------------------------------------------------------------------- publish
def publish_specs(specs: Sequence[TaskSpec], *, grid: Grid, admitted: Sequence[str] = (), now: float | None = None) -> dict[str, Any]:
    """Append one TASK record per new spec, per partition, through ``log.outbox.Appender``.

    The frontier (``log.frontier.derive``) says what is already published or done in each
    partition; a spec whose task id is published is skipped (idempotent publish), one that is
    done in the log or has a verified result pointer in the object store (``tasks.results.is_done``:
    identical-basis re-run = cache hit, U66) is counted ``cached``.  Refuses a spec whose basis is
    not admitted when an admitted set is configured (§1.5 graft a).
    """
    results = _import("agentdecompile_grid.tasks.results")
    records = _import("agentdecompile_grid.log.records")
    admitted_set = {str(b) for b in admitted}
    by_partition: dict[str, list[TaskSpec]] = {}
    for spec in specs:
        if admitted_set and spec.basis_hash not in admitted_set:
            raise Refused(f"basis-not-admitted:{spec.basis_hash[:12]}")
        if spec.kind in TASK_KINDS:
            check_basis_projection(TASK_KINDS.get(spec.kind), spec)   # U158: publish refuses a projection mismatch by name
        by_partition.setdefault(spec.partition_key, []).append(spec)
    summary: dict[str, Any] = {"planned": len(specs), "published": 0, "existing": 0, "cached": 0, "partitions": {}}
    objects = grid.objects()
    appender = grid.appender()
    for partition, group in sorted(by_partition.items()):
        report = grid.derive(partitions=[partition], now=now)
        published = set(report.kinds_of) - set(report.orphans)   # a RESULT/INTENT without a TASK record is not a publish
        done = set(report.done)
        drafts = []
        for spec in group:
            if spec.task_id in published:
                summary["existing"] += 1
                continue
            if spec.task_id in done or results.is_done(objects, spec.task_id):
                summary["cached"] += 1
                continue
            drafts.append(records.Draft(RecordType.TASK, spec.to_record(), spec.basis_hash))
            published.add(spec.task_id)
        if not drafts:
            summary["partitions"][partition] = {"published": 0, "head": appender.head(partition)[0]}
            continue
        try:
            landed = appender.append(partition, drafts)
        except GridError as exc:
            raise HeadConflict(f"append-failed:{partition}:{type(exc).__name__}") from exc
        summary["published"] += len(landed)
        summary["partitions"][partition] = {"published": len(landed), "head": landed[-1].seq, "seqs": [r.seq for r in landed]}
    return summary


def cmd_publish(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    lanes = load_lanes(grid.cfg)
    try:
        kind_cls = TASK_KINDS.get(args.kind)
    except KeyError:
        raise NoSuchKind(f"no task kind {args.kind!r}; known: {TASK_KINDS.names()} (lanes loaded: {lanes})") from None
    plan = getattr(kind_cls, "plan", None)
    if plan is None:
        raise Refused(f"kind-has-no-planner:{args.kind}")
    options = parse_options(args.option)
    if args.subject:
        options["subject"] = args.subject
    specs = plan(
        grid.objects(), args.snapshot, basis_hash=args.basis_hash, shard_size=args.shard_size,
        max_budget=BudgetClass(args.allow_budget), scratch=str(grid.root / "scratch" / "publish"), **options,
    )
    summary = publish_specs(specs, grid=grid, admitted=list(grid.cfg.admitted_bases))
    summary.update({
        "kind": args.kind, "basis_hash": specs[0].basis_hash if specs else "", "lanes": lanes,
        "budgets": sorted({s.budget.value for s in specs}), "task_ids": [s.task_id for s in specs] if args.json else len(specs),
    })
    emit(summary, as_json=args.json)
    return 0


# --------------------------------------------------------------------------- work / verify
def _node_loop(grid: Grid, *, kind: str, node: str | None, role: str | None, kinds: Sequence[str], claimed: Sequence[str] = ()) -> Any:
    """Build a ``WorkLoop`` (``kind="work"``) or ``VerifierLoop`` (``kind="verify"``) for one node identity."""
    agent = _import("agentdecompile_grid.worker.agent")
    loop_mod = _import("agentdecompile_grid.worker.loop")
    outbox_mod = _import("agentdecompile_grid.worker.outbox")
    sandbox_mod = _import("agentdecompile_grid.worker.sandbox")
    identity_mod = _import("agentdecompile_grid.worker.identity")
    cfg = grid.cfg
    verifying = kind == "verify"
    name = node or (cfg.verifier.node_name if verifying else cfg.worker.node_name)
    role = role or (cfg.verifier.role if verifying else cfg.worker.role)
    state_dir = Path(cfg.node_state_dir(name))
    objects, log, heads = grid.objects(), grid.log(), grid.heads()
    key, identity, report = agent.open_node_identity(state_dir, role=role, objects=objects, claimed=claimed, key_algorithm=cfg.worker.key_algorithm,
                                                     key_lifetime_s=cfg.identity.key_lifetime_s, renew_after_canary=cfg.identity.renew_after_canary)
    signer = identity_mod.NodeSigner(key)
    upstream = loop_mod.Upstream(objects, agent.record_writer(log, heads, signer, backoff=_import("agentdecompile_grid.log.backoff").BackoffPolicy.from_config(cfg.to_mapping("backoff"))))
    outbox = outbox_mod.Outbox(state_dir / "outbox", max_entries=cfg.outbox.max_entries)
    identity_mod.enqueue_announce(outbox, identity_mod.NodeKeyStore(state_dir), key, identity, partition=cfg.keyring.announce_partition)   # KEY_ANNOUNCE once per key
    sandbox = sandbox_mod.SubprocessSandbox(state_dir / "work")
    policy = grid.frontier_policy()
    filters = grid.record_filters()
    frontier = _import("agentdecompile_grid.log.frontier")
    wanted = list(kinds) or None
    common = dict(identity=identity, sandbox=sandbox, outbox=outbox, objects=objects, upstream=upstream,
                  frontier=lambda: frontier.derive(log, objects, time.time(), policy=policy, kinds=wanted, filters=filters),
                  store_locator=grid.transport.locator(), log=log)
    imports = import_modules_for_children(cfg)
    if verifying:
        verify_loop = _import("agentdecompile_grid.verify.loop")
        policy_mod = _import("agentdecompile_grid.verify.policy")
        records = _import("agentdecompile_grid.worker.records")
        vconfig = verify_loop.VerifierConfig.from_grid_config(cfg, lanes=wanted, import_modules=imports)
        loop = verify_loop.VerifierLoop(task_lookup=records.LogTaskIndex(log), config=vconfig,
                                        penalties=policy_mod.PenaltyLedger.load(objects), revocations=policy_mod.RevocationList.load(objects), **common)
    else:
        config = loop_mod.WorkerConfig.from_grid_config(cfg, lanes=wanted, import_modules=imports, cores=1)
        loop = loop_mod.WorkLoop(config=config, **common)
    loop.node = {"name": name, "state_dir": str(state_dir), "key_id": identity.key_id, "role": identity.role, "capabilities": list(identity.capabilities),
                 "canaries": report.to_record() if report is not None else "saved-identity"}
    return loop


def _run_loop(loop: Any, args: argparse.Namespace) -> int:
    if args.once:
        report = loop.run_once(max_wall_s=args.max_wall_s)
        report["node"] = loop.node
        emit(report, as_json=args.json)
        return 0
    steps = loop.drive(max_steps=None)
    emit({"steps": steps, "node": loop.node, "status": loop.status()}, as_json=args.json)
    return 0


def cmd_work(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    load_lanes(grid.cfg)
    kinds = [k for k in (args.kinds or "").split(",") if k]
    loop = _node_loop(grid, kind="work", node=args.node, role=args.role, kinds=kinds, claimed=tuple(args.capability or ()))
    return _run_loop(loop, args)


def cmd_verify(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    load_lanes(grid.cfg)
    kinds = [k for k in (args.kinds or "").split(",") if k]
    loop = _node_loop(grid, kind="verify", node=args.node, role=args.role, kinds=kinds, claimed=tuple(args.capability or ()))
    return _run_loop(loop, args)


# --------------------------------------------------------------------------- view
def cmd_view(args: argparse.Namespace) -> int:
    from . import view as view_pkg  # registers the appliers

    if args.view_cmd == "status":
        con = view_pkg.open_view(args.db)
        try:
            rows = [dict(r) for r in con.execute("SELECT partition, seq, basis_hash, state FROM grid_view_position ORDER BY partition")]
        finally:
            con.close()
        emit({"db": str(args.db), "partitions": rows}, as_json=args.json)
        return 0
    grid = Grid.open(args)
    load_lanes(grid.cfg)   # hooks register on import
    if args.applier != view_pkg.SQLiteViewApplier.name:
        try:
            applier_cls = APPLIERS.get(args.applier)
        except KeyError:
            raise NoSuchKind(f"no view applier {args.applier!r}; known: {APPLIERS.names()}") from None
        applier = applier_cls({}, partition=(args.partition or [""])[0]) if args.applier == "similarity" else applier_cls()
        applier.apply([], grid.objects())   # declared appliers refuse here by name
        return 0
    report = view_pkg.materialize(grid.root, args.db, partitions=args.partition or None, resume=bool(args.resume),
                                  objects=grid.objects(), log=grid.log())
    emit(report, as_json=args.json)
    # a stale partition or a skipped VERIFIED record (contract mismatch with the log slice) is
    # a non-zero exit, never a quietly empty view
    return 1 if report.get("stale") or report.get("events") else 0


# --------------------------------------------------------------------------- fleet
def cmd_fleet(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    fleet = _import("agentdecompile_grid.fleet")
    try:
        PROVIDERS.get(args.provider)
    except KeyError:
        raise NoSuchKind(f"no fleet provider {args.provider!r}; known: {PROVIDERS.names()}") from None
    lanes = [lane for lane in (args.lanes or "").split(",") if lane] or list(grid.cfg.fleet.lanes)
    labels = {"role": args.role, "lanes": ",".join(lanes), "grid": __version__}
    objects = grid.objects()
    provider_config = dict(grid.cfg.fleet.provider_config)
    if args.fleet_cmd == "status":
        emit({"provider": args.provider, **fleet.fleet_status(objects)} if hasattr(fleet, "fleet_status") else {"provider": args.provider}, as_json=args.json)
        return 0
    if args.fleet_cmd in ("up", "replace"):
        join_url = args.join_url or os.environ.get(INVITE_ENV, "") or grid.cfg.join_url
        if not join_url:
            raise NotConfigured(f"fleet up needs --join-url, ${INVITE_ENV} or GridConfig.join_url (the invite carries the role)")
        if args.fleet_cmd == "replace":
            fleet.fleet_down(objects, list(args.node or ()), provider=args.provider, provider_config=provider_config)
        node_ids, manifest_ref = fleet.fleet_up(objects, join_url, provider=args.provider, count=int(args.count), role=args.role, lanes=lanes, labels=labels,
                                                provider_config=provider_config, user_data_format=grid.cfg.fleet.user_data_format or None, fabric_id=grid.cfg.fleet.fabric_id)
        emit({"provider": args.provider, "created": list(node_ids), "labels": labels, "manifest": str(manifest_ref)}, as_json=args.json)
        return 0
    if args.fleet_cmd == "down":
        manifest_ref = fleet.fleet_down(objects, list(args.node or ()), provider=args.provider, provider_config=provider_config)
        emit({"provider": args.provider, "down": list(args.node or ()), "manifest": str(manifest_ref)}, as_json=args.json)
        return 0
    raise UsageError(f"unknown fleet verb {args.fleet_cmd!r}")


# --------------------------------------------------------------------------- objects / log
def cmd_objects(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    store = grid.objects()
    if args.objects_cmd == "put":
        put_path = getattr(store, "put_path", None)
        ref = put_path(args.file) if callable(put_path) else store.put(Path(args.file).read_bytes())
        emit({"ref": str(ref), "bytes": store.size(ref)}, as_json=args.json)
        return 0
    if args.objects_cmd == "get":
        ref = ObjectRef(args.ref if args.ref.startswith("sha256:") else f"sha256:{args.ref}")
        if not store.exists(ref):
            raise Refused(f"object-missing:{ref.hex[:12]}")
        if args.out:
            get_path = getattr(store, "get_path", None)
            if callable(get_path):
                get_path(ref, args.out)
            else:
                Path(args.out).write_bytes(store.get(ref))
            emit({"ref": str(ref), "bytes": store.size(ref), "out": "written"}, as_json=args.json)
        else:
            sys.stdout.buffer.write(store.get(ref))
        return 0
    if args.objects_cmd == "gc":
        gc = getattr(store, "gc", None)
        if gc is None:
            raise NotConfigured(f"object store {getattr(store, 'name', '?')!r} has no gc(); LocalDirStore does")
        gc_mod = _import("agentdecompile_grid.objects.gc")
        keep = gc_mod.StaticPins(_referenced_refs(grid.log()))   # inputs are named only by TASK bodies: the log is a pin source
        report = gc(dry_run=bool(args.dry_run), extra_pins=[keep])
        emit(report.to_dict() if hasattr(report, "to_dict") else {"report": str(report)}, as_json=args.json)
        return 0
    raise UsageError(f"unknown objects verb {args.objects_cmd!r}")


def _referenced_refs(log: Any) -> set[ObjectRef]:
    """Every ref a log record body names (inputs, outputs, result_ref, evidence_ref): what GC must keep."""
    keep: set[ObjectRef] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str) and value.startswith("sha256:") and len(value) == 71:
            keep.add(ObjectRef(value))
        elif isinstance(value, Mapping):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    for partition in log.partitions():
        for rec in log.read(partition, since_seq=0):
            walk(rec.body)
    return keep


def cmd_log(args: argparse.Namespace) -> int:
    grid = Grid.open(args)
    log = grid.log()
    if args.log_cmd != "tail":
        raise UsageError(f"unknown log verb {args.log_cmd!r}")
    last = log.last_seq(args.partition)
    since = args.since if args.since is not None else max(0, last - args.limit)
    rows = [rec.to_record() for rec in log.read(args.partition, since_seq=since)]
    for row in rows[-args.limit:]:
        print(json.dumps(row, sort_keys=True, default=str))
    return 0


# --------------------------------------------------------------------------- describe
def _describe_item(item: Any) -> Any:
    describe = getattr(item, "describe", None)
    if callable(describe):
        try:
            return describe()
        except GridError as exc:
            return {"error": f"{type(exc).__name__}: {scrub(str(exc))}"}
        except TypeError:
            return {"name": getattr(item, "name", str(item))}
    return {"name": getattr(item, "name", str(item))}


def cmd_describe(args: argparse.Namespace) -> int:
    notes: dict[str, str] = {}
    try:
        lanes = load_lanes()
    except GridError as exc:
        lanes = []
        notes["lanes"] = f"{type(exc).__name__}: {scrub(str(exc))}"
    from . import view as _view  # noqa: F401  (registers appliers)

    for module in ("agentdecompile_grid.objects", "agentdecompile_grid.log", "agentdecompile_grid.worker",
                   "agentdecompile_grid.verify", "agentdecompile_grid.fleet.providers", "agentdecompile_grid.transport",
                   "agentdecompile_grid.tasks"):
        try:
            importlib.import_module(module)
        except ImportError:
            notes[module] = "not present in this checkout yet"
        except Exception as exc:
            notes[module] = f"{type(exc).__name__}"
    registries = {
        "task_kinds": TASK_KINDS, "object_stores": OBJECT_STORES, "log_stores": LOG_STORES, "head_stores": HEAD_STORES,
        "signers": SIGNERS, "canaries": CANARIES, "verifiers": VERIFIERS, "appliers": APPLIERS, "providers": PROVIDERS,
        "transports": TRANSPORTS,
    }
    report: dict[str, Any] = {"version": __version__, "lanes": lanes, "lane_sources": lane_module_names(), "notes": notes}
    for name, registry in registries.items():
        report[name] = {item_name: _describe_item(item) for item_name, item in registry.items()} if args.verbose else registry.names()
    report["basis_projections"] = _import("agentdecompile_grid.tasks.registry").projection_table()   # U158: {kind: basis_fields}
    if args.verbose:
        try:
            config_mod = _import("agentdecompile_grid.config")
            report["config"] = config_mod.describe(load_config(getattr(args, "root", None)))
        except GridError as exc:
            report["config"] = {"error": f"{type(exc).__name__}: {scrub(str(exc))}"}
    emit(report, as_json=args.json)
    return 0


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adgrid", description="agentdecompile grid: content-addressed, log-structured distributed compute")
    parser.add_argument("--version", action="version", version=f"adgrid {__version__}")
    parser.add_argument("--root", help=f"grid root directory (default: ${ROOT_ENV} or GridConfig paths.root)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    join = sub.add_parser("join", help="attach to (or bootstrap) the local agent and join a grid")
    join.add_argument("url", nargs="?", help=f"invite url (default: ${INVITE_ENV})")
    join.add_argument("--with", dest="with_", nargs="+", action="append", metavar="LANE", help="toolchain <hash> | analyzer")
    join.add_argument("--toolchain-path", help="a toolchain tree this node already owns (hashed by canary)")
    join.add_argument("--idle-only", action="store_true")
    join.add_argument("--cores", type=int)
    join.add_argument("--node", help="node state directory name under <root>/nodes (default: worker.node_name)")
    join.add_argument("--no-run", action="store_true", help="bootstrap and return instead of driving the agent")
    join.set_defaults(fn=cmd_join)

    sub.add_parser("leave", help="drop intents and detach").set_defaults(fn=cmd_leave)
    sub.add_parser("status", help="local agent status").set_defaults(fn=cmd_status)

    publish = sub.add_parser("publish", help="plan and publish tasks of one kind from a store snapshot")
    publish.add_argument("kind")
    publish.add_argument("--snapshot", required=True, help="store path (VACUUM INTO copy is made), TU dir, manifest, file, or sha256:ref")
    publish.add_argument("--basis-hash", help="must equal the snapshot's own basis when the snapshot is a store")
    publish.add_argument("--shard-size", type=int, default=512)
    publish.add_argument("--allow-budget", choices=[b.value for b in BudgetClass if b != BudgetClass.UNBOUNDED], default=BudgetClass.SMALL.value,
                         help="highest budget class a planned task may have (never-awaited rule; default small)")
    publish.add_argument("--option", action="append", metavar="KEY=VALUE", help="planner option (toolchain_identity_hash=..., src=..., passes=a,b)")
    publish.add_argument("--subject", help="partition subject (default: the kind)")
    publish.set_defaults(fn=cmd_publish)

    for verb, fn, helptext in (("work", cmd_work, "step the work loop"), ("verify", cmd_verify, "step the verifier loop")):
        p = sub.add_parser(verb, help=helptext)
        p.add_argument("--once", action="store_true", help="one task (or nothing eligible), then flush and stop")
        p.add_argument("--kinds", help="comma-separated kinds to accept (default: every registered kind)")
        p.add_argument("--capability", action="append", help="capability this node claims beyond what its canaries prove")
        p.add_argument("--node", help="node state directory name under <root>/nodes (default: worker/verifier node_name)")
        p.add_argument("--role", choices=["donor", "fleet", "operator"], help="role of a self-rooted identity (default: worker/verifier role)")
        p.add_argument("--max-wall-s", type=float, help="--once: stop after this many seconds even if the task is still running")
        p.set_defaults(fn=fn)

    view = sub.add_parser("view", help="materialized views")
    view_sub = view.add_subparsers(dest="view_cmd", required=True)
    mat = view_sub.add_parser("materialize", help="replay the verified stream into a SQLite view (from record 1)")
    mat.add_argument("db")
    mat.add_argument("--partition", action="append")
    mat.add_argument("--resume", action="store_true", help="continue from the stored position instead of rebuilding")
    mat.add_argument("--applier", default="sqlite", help="view applier (sqlite | similarity)")
    vstat = view_sub.add_parser("status", help="per-partition position and named state of a view")
    vstat.add_argument("db")
    view.set_defaults(fn=cmd_view)

    fleet = sub.add_parser("fleet", help="operator fleet bootstrap")
    fleet.add_argument("fleet_cmd", choices=["up", "down", "status", "replace"])
    fleet.add_argument("--provider", required=True)
    fleet.add_argument("--count", type=int, default=1)
    fleet.add_argument("--lanes", help="comma-separated lanes (analyzer,toolchain)")
    fleet.add_argument("--role", default="fleet", choices=["fleet", "donor", "operator"])
    fleet.add_argument("--join-url")
    fleet.add_argument("--node", action="append", help="node id for down/replace")
    fleet.set_defaults(fn=cmd_fleet)

    objects = sub.add_parser("objects", help="content-addressed object store")
    objects_sub = objects.add_subparsers(dest="objects_cmd", required=True)
    objects_sub.add_parser("put").add_argument("file")
    get = objects_sub.add_parser("get")
    get.add_argument("ref")
    get.add_argument("--out")
    gc = objects_sub.add_parser("gc", help="one GC sweep under the store's lock")
    gc.add_argument("--dry-run", action="store_true")
    objects.set_defaults(fn=cmd_objects)

    log = sub.add_parser("log", help="per-partition logs")
    log_sub = log.add_subparsers(dest="log_cmd", required=True)
    tail = log_sub.add_parser("tail")
    tail.add_argument("partition")
    tail.add_argument("--since", type=int)
    tail.add_argument("--limit", type=int, default=20)
    log.set_defaults(fn=cmd_log)

    describe = sub.add_parser("describe", help="every registry and adapter")
    describe.add_argument("--verbose", "-v", action="store_true", help="describe() of every item and the configuration")
    describe.set_defaults(fn=cmd_describe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        load_builtin_kinds()
        return int(args.fn(args))
    except GridError as exc:
        print(f"error: {type(exc).__name__}: {scrub(str(exc))}", file=sys.stderr)
        if os.environ.get("ADGRID_DEBUG"):
            raise
        return int(getattr(exc, "exit_code", 2))
    except KeyboardInterrupt:
        print("error: Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # never a traceback at the edge
        if os.environ.get("ADGRID_DEBUG"):
            raise
        print(f"error: {Unexpected.__name__}: {type(exc).__name__}: {scrub(str(exc))[:200]}", file=sys.stderr)
        return Unexpected.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
