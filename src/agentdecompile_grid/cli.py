"""``adgrid`` -- the one command every node runs (design §1.3, §8 U120/U125/U128/U129).

Thin dispatch over the registries in ``core``: every verb resolves adapters by name and never
holds pipeline state.  The grid never imports the recovery package; lane modules (the
pipeline's task kinds) are loaded **by name** from, in order, ``GridConfig.lanes``, the
``ADGRID_LANES`` environment variable (``os.pathsep``- or comma-separated module names) and the
``agentdecompile_grid.lanes`` entry-point group.  ``publish`` reaches a lane's planner through
``TASK_KINDS.get(kind).plan(...)`` (duck-typed), never through a literal import.

Verbs::

    adgrid join <url> [--with toolchain <hash> | --toolchain-path DIR] [--with analyzer] [--idle-only] [--cores N]
    adgrid leave | status
    adgrid publish <kind> --snapshot PATH|sha256:... [--basis-hash H] [--shard-size N]
                          [--allow-budget small|medium|large] [--option k=v ...] [--subject S]
    adgrid work [--once] [--kinds a,b]      adgrid verify [--once]
    adgrid view materialize <db> [--partition P ...] [--resume] [--applier sqlite]
    adgrid view status <db>
    adgrid fleet up|down|status|replace --provider NAME --count N --lanes a,b [--role fleet] [--node ID ...]
    adgrid objects put FILE | get REF [--out FILE] | gc
    adgrid log tail <partition> [--since N] [--limit N]
    adgrid describe [--json]

Errors: every failure is a ``GridError`` subclass printed as ``error: <Class>: <message>`` with
the class's exit code -- never a traceback (``ADGRID_DEBUG=1`` re-raises for development).
Unexpected exceptions are reported by type only.  Messages never carry a plaintext slug (lanes
hash them) and absolute paths are scrubbed at the edge.

Attach-first (user rule: exclusive lock is not join): ``join``/``leave``/``status`` delegate to
``worker.agent``, which attaches to a running local agent before it would ever start one, and
reports ``EADDRINUSE`` as ``AlreadyOwned`` (exit 3), never as a retry.

Names assumed from the other slices are collected in ``ASSUMED`` so the integrator can fix
mismatches in one place.

Acceptance tests (named, landed in the verification phase):

* ``test_cli_no_recovery_import`` -- a grep for the recovery package's name under the grid package is empty;
* ``test_cli_every_error_is_named_and_coded`` -- no traceback on any refusal; exit codes match;
* ``test_cli_publish_derives_basis_from_snapshot`` and ``test_cli_publish_refuses_foreign_basis``;
* ``test_cli_publish_is_idempotent`` -- a second publish of the same snapshot publishes nothing;
* ``test_cli_describe_lists_every_registry`` (with and without lanes loaded);
* ``test_cli_view_materialize_twice_identical_dump``;
* ``test_cli_join_attaches_never_starts`` (U125).
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import os
import re
import sys
from collections import defaultdict
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
    Record,
    RecordType,
    Refused,
    TaskSpec,
    canonical_json,
)

#: Names this CLI assumes from the other slices (the integrator wires the final names).
ASSUMED: Mapping[str, str] = {
    "agentdecompile_grid.objects.local.LocalDirStore(root)": "ObjectStore over a local directory",
    "agentdecompile_grid.log.local.LocalFileLog(root)": "LogStore over local files",
    "agentdecompile_grid.log.heads.LocalFileHeads(root)": "HeadStore with CAS over local files",
    "agentdecompile_grid.log.signing.NullSigner()": "Signer with key_id, hash-chain only",
    "agentdecompile_grid.log.frontier.derive(log, objects, partition=..., now=...)": "Frontier",
    "agentdecompile_grid.worker.agent.join(url, *, capabilities, toolchain_path, idle_only, cores, root)": "attach-first join -> status mapping",
    "agentdecompile_grid.worker.agent.leave(root=...)": "drop intents; returns mapping",
    "agentdecompile_grid.worker.agent.status(root=...)": "returns mapping",
    "agentdecompile_grid.worker.loop.WorkLoop(transport, *, signer, kinds, capabilities).run(once=bool)": "returns mapping",
    "agentdecompile_grid.verify.loop.VerifierLoop(transport, *, signer).run(once=bool)": "returns mapping",
    "agentdecompile_grid.fleet.providers": "module whose import fills core.PROVIDERS; adapters take an optional config mapping",
    "agentdecompile_grid.fleet.cloudinit.render(join_url, *, role, lanes)": "user-data text",
    "agentdecompile_grid.tasks.builtin.SubprocessVerb": "builtin runner for SubprocessVerb-style params",
    "agentdecompile_grid.config.GridConfig.load(path=None)": "attributes root, lanes, join_url, admitted_bases",
    "ObjectStore.get_named('results/<task_id>')": "non-None when a result index entry exists (cache hit)",
    "ObjectStore.gc(*, keep=iterable_of_refs)": "optional; NotConfigured otherwise",
    "ObjectStore.put_path(path) -> ref / get_path(ref, path)": "optional streaming fast paths the lanes use for GB-sized snapshots",
    "TaskKind.plan(objects, snapshot, *, basis_hash, shard_size, max_budget, **options) -> list[TaskSpec]": "lane planners (duck-typed)",
}

LANES_ENV = "ADGRID_LANES"
ROOT_ENV = "ADGRID_ROOT"
LANES_ENTRY_POINT_GROUP = "agentdecompile_grid.lanes"

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


# --------------------------------------------------------------------------- lazy adapters
def _import(module: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise NotConfigured(f"{module} not present in this checkout yet") from exc


def _config():
    """``GridConfig.load()`` or ``None`` when the config slice is absent."""
    try:
        mod = importlib.import_module("agentdecompile_grid.config")
    except ImportError:
        return None
    loader = getattr(getattr(mod, "GridConfig", None), "load", None)
    if loader is None:
        return None
    try:
        return loader()
    except GridError:
        raise
    except Exception:
        return None


def resolve_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ROOT_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    cfg = _config()
    root = getattr(cfg, "root", None) if cfg is not None else None
    if root:
        return Path(str(root)).expanduser()
    raise NotConfigured(f"grid root not set: pass --root, set {ROOT_ENV}, or configure GridConfig.root")


def _objects(root: Path):
    return _import("agentdecompile_grid.objects.local").LocalDirStore(root)


def _log(root: Path):
    return _import("agentdecompile_grid.log.local").LocalFileLog(root)


def _heads(root: Path):
    return _import("agentdecompile_grid.log.heads").LocalFileHeads(root)


def _signer():
    return _import("agentdecompile_grid.log.signing").NullSigner()


class LocalTransport:
    """The ``Transport`` Protocol over the local adapters: what ``work``/``verify`` are handed."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def objects(self):
        return _objects(self.root)

    def log(self):
        return _log(self.root)

    def heads(self):
        return _heads(self.root)


# --------------------------------------------------------------------------- lanes
def lane_module_names() -> list[str]:
    names: list[str] = []
    cfg = _config()
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


def load_lanes() -> list[str]:
    """Import every configured lane module (each registers its kinds on import)."""
    loaded: list[str] = []
    for name in lane_module_names():
        try:
            importlib.import_module(name)
        except GridError:
            raise
        except Exception as exc:
            raise LaneImportFailed(f"lane module {name!r}: {type(exc).__name__}") from exc
        loaded.append(name)
    return loaded


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


# --------------------------------------------------------------------------- verbs
def cmd_join(args: argparse.Namespace) -> int:
    capabilities: list[str] = []
    for entry in args.with_ or ():
        if entry[0] == "toolchain":
            if len(entry) != 2:
                raise UsageError("--with toolchain needs a hash")
            capabilities.append(f"toolchain:{entry[1]}")
        elif entry[0] == "analyzer":
            capabilities.append("analyzer")
        else:
            raise UsageError(f"unknown --with lane {entry[0]!r} (toolchain <hash> | analyzer)")
    agent = _import("agentdecompile_grid.worker.agent")
    result = agent.join(
        args.url, capabilities=tuple(capabilities), toolchain_path=args.toolchain_path,
        idle_only=bool(args.idle_only), cores=args.cores, root=_root_or_none(args),
    )
    emit(result, as_json=args.json)
    return 0


def _root_or_none(args: argparse.Namespace) -> Path | None:
    try:
        return resolve_root(args.root)
    except NotConfigured:
        return None


def cmd_leave(args: argparse.Namespace) -> int:
    agent = _import("agentdecompile_grid.worker.agent")
    emit(agent.leave(root=_root_or_none(args)), as_json=args.json)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    agent = _import("agentdecompile_grid.worker.agent")
    emit(agent.status(root=_root_or_none(args)), as_json=args.json)
    return 0


def _sign(rec: Record, signer) -> Record:
    payload = canonical_json(rec.to_record(include_signature=False))
    return dataclasses.replace(rec, signature=signer.sign(payload))


def publish_specs(specs: Sequence[TaskSpec], *, objects, log, heads, signer, admitted: Sequence[str] = ()) -> dict[str, Any]:
    """Append one TASK record per new spec, per partition, through the head CAS.

    Skips a spec whose task id is already published in its partition (idempotent publish) or
    whose result index entry exists (identical-basis re-run = cache hit, U66).  Refuses a spec
    whose basis is not admitted when an admitted set is configured (§1.5 graft a).
    """
    admitted_set = {str(b) for b in admitted}
    by_partition: dict[str, list[TaskSpec]] = defaultdict(list)
    for spec in specs:
        if admitted_set and spec.basis_hash not in admitted_set:
            raise Refused(f"basis-not-admitted:{spec.basis_hash[:12]}")
        by_partition[spec.partition_key].append(spec)
    summary: dict[str, Any] = {"planned": len(specs), "published": 0, "existing": 0, "cached": 0, "partitions": {}}
    for partition, group in sorted(by_partition.items()):
        existing = {
            str(rec.body.get("task_id", "")) for rec in log.read(partition, since_seq=0) if rec.type == RecordType.TASK
        }
        seq, prev = heads.get(partition)
        batch: list[Record] = []
        for spec in group:
            if spec.task_id in existing:
                summary["existing"] += 1
                continue
            if objects.get_named(f"results/{spec.task_id}") is not None:
                summary["cached"] += 1
                continue
            seq += 1
            rec = Record(
                partition=partition, seq=seq, type=RecordType.TASK, body=spec.to_record(), prev=prev,
                signer_key=signer.key_id, signature="", basis_hash=spec.basis_hash,
            )
            rec = _sign(rec, signer)
            prev = rec.digest()
            batch.append(rec)
            existing.add(spec.task_id)
        if not batch:
            summary["partitions"][partition] = {"published": 0, "head": seq}
            continue
        expected = heads.get(partition)
        log.append(batch)
        if not heads.cas(partition, expected, (batch[-1].seq, batch[-1].digest())):
            raise HeadConflict(f"head-cas-failed:{partition}:expected-seq-{expected[0]}")
        summary["published"] += len(batch)
        summary["partitions"][partition] = {"published": len(batch), "head": batch[-1].seq}
    return summary


def cmd_publish(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    lanes = load_lanes()
    try:
        kind_cls = TASK_KINDS.get(args.kind)
    except KeyError:
        raise NoSuchKind(f"no task kind {args.kind!r}; known: {TASK_KINDS.names()} (lanes loaded: {lanes})") from None
    plan = getattr(kind_cls, "plan", None)
    if plan is None:
        raise Refused(f"kind-has-no-planner:{args.kind}")
    objects, log, heads, signer = _objects(root), _log(root), _heads(root), _signer()
    options = parse_options(args.option)
    if args.subject:
        options["subject"] = args.subject
    specs = plan(
        objects, args.snapshot, basis_hash=args.basis_hash, shard_size=args.shard_size,
        max_budget=BudgetClass(args.allow_budget), scratch=str(root / "scratch" / "publish"), **options,
    )
    cfg = _config()
    admitted = list(getattr(cfg, "admitted_bases", None) or ()) if cfg is not None else []
    summary = publish_specs(specs, objects=objects, log=log, heads=heads, signer=signer, admitted=admitted)
    summary.update({
        "kind": args.kind, "basis_hash": specs[0].basis_hash if specs else "", "lanes": lanes,
        "budgets": sorted({s.budget.value for s in specs}), "task_ids": [s.task_id for s in specs] if args.json else len(specs),
    })
    emit(summary, as_json=args.json)
    return 0


def cmd_work(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    load_lanes()
    loop_mod = _import("agentdecompile_grid.worker.loop")
    kinds = [k for k in (args.kinds or "").split(",") if k] or TASK_KINDS.names()
    loop = loop_mod.WorkLoop(LocalTransport(root), signer=_signer(), kinds=kinds, capabilities=tuple(args.capability or ()))
    emit(loop.run(once=bool(args.once)), as_json=args.json)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    load_lanes()
    loop_mod = _import("agentdecompile_grid.verify.loop")
    loop = loop_mod.VerifierLoop(LocalTransport(root), signer=_signer())
    emit(loop.run(once=bool(args.once)), as_json=args.json)
    return 0


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
    root = resolve_root(args.root)
    load_lanes()   # hooks register on import
    if args.applier != view_pkg.SQLiteViewApplier.name:
        try:
            applier_cls = APPLIERS.get(args.applier)
        except KeyError:
            raise NoSuchKind(f"no view applier {args.applier!r}; known: {APPLIERS.names()}") from None
        applier = applier_cls({}, partition=(args.partition or [""])[0]) if args.applier == "similarity" else applier_cls()
        applier.apply([], _objects(root))   # declared appliers refuse here by name
        return 0
    report = view_pkg.materialize(root, args.db, partitions=args.partition or None, resume=bool(args.resume))
    emit(report, as_json=args.json)
    return 1 if report.get("stale") else 0


def cmd_fleet(args: argparse.Namespace) -> int:
    _import("agentdecompile_grid.fleet.providers")     # fills PROVIDERS on import
    try:
        adapter_cls = PROVIDERS.get(args.provider)
    except KeyError:
        raise NoSuchKind(f"no fleet provider {args.provider!r}; known: {PROVIDERS.names()}") from None
    adapter = adapter_cls()
    lanes = [lane for lane in (args.lanes or "").split(",") if lane]
    labels = {"role": args.role, "lanes": ",".join(lanes), "grid": __version__}
    if args.fleet_cmd == "status":
        emit({"provider": args.provider, "nodes": list(adapter.status())}, as_json=args.json)
        return 0
    if args.fleet_cmd in ("up", "replace"):
        cfg = _config()
        join_url = args.join_url or (getattr(cfg, "join_url", None) if cfg is not None else None)
        if not join_url:
            raise NotConfigured("fleet up needs --join-url or GridConfig.join_url (the invite carries the role)")
        user_data = _import("agentdecompile_grid.fleet.cloudinit").render(join_url, role=args.role, lanes=lanes)
        if args.fleet_cmd == "replace":
            adapter.down(list(args.node or ()))
        created = list(adapter.up(int(args.count), user_data, labels))
        emit({"provider": args.provider, "created": created, "labels": labels}, as_json=args.json)
        return 0
    if args.fleet_cmd == "down":
        adapter.down(list(args.node or ()))
        emit({"provider": args.provider, "down": list(args.node or ())}, as_json=args.json)
        return 0
    raise UsageError(f"unknown fleet verb {args.fleet_cmd!r}")


def cmd_objects(args: argparse.Namespace) -> int:
    root = resolve_root(args.root)
    store = _objects(root)
    if args.objects_cmd == "put":
        ref = store.put(Path(args.file).read_bytes())
        emit({"ref": str(ref), "bytes": store.size(ref)}, as_json=args.json)
        return 0
    if args.objects_cmd == "get":
        ref = ObjectRef(args.ref if args.ref.startswith("sha256:") else f"sha256:{args.ref}")
        if not store.exists(ref):
            raise Refused(f"object-missing:{ref.hex[:12]}")
        data = store.get(ref)
        if args.out:
            Path(args.out).write_bytes(data)
            emit({"ref": str(ref), "bytes": len(data), "out": "written"}, as_json=args.json)
        else:
            sys.stdout.buffer.write(data)
        return 0
    if args.objects_cmd == "gc":
        gc = getattr(store, "gc", None)
        if gc is None:
            raise NotConfigured("agentdecompile_grid.objects.local.LocalDirStore.gc not present in this checkout yet")
        emit(gc(keep=_referenced_refs(root)), as_json=args.json)
        return 0
    raise UsageError(f"unknown objects verb {args.objects_cmd!r}")


def _referenced_refs(root: Path) -> set[str]:
    """Every ref named by a log record body (inputs, outputs, result_ref): what GC must keep."""
    log = _log(root)
    keep: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str) and value.startswith("sha256:"):
            keep.add(value)
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
    root = resolve_root(args.root)
    log = _log(root)
    if args.log_cmd != "tail":
        raise UsageError(f"unknown log verb {args.log_cmd!r}")
    last = log.last_seq(args.partition)
    since = args.since if args.since is not None else max(0, last - args.limit)
    rows = [rec.to_record() for rec in log.read(args.partition, since_seq=since)]
    for row in rows[-args.limit:]:
        print(json.dumps(row, sort_keys=True, default=str))
    return 0


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
    if args.verbose:
        report["assumed"] = dict(ASSUMED)
    emit(report, as_json=args.json)
    return 0


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adgrid", description="agentdecompile grid: content-addressed, log-structured distributed compute")
    parser.add_argument("--version", action="version", version=f"adgrid {__version__}")
    parser.add_argument("--root", help=f"grid root directory (default: ${ROOT_ENV} or GridConfig.root)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    join = sub.add_parser("join", help="attach to (or bootstrap) the local agent and join a grid")
    join.add_argument("url")
    join.add_argument("--with", dest="with_", nargs="+", action="append", metavar="LANE", help="toolchain <hash> | analyzer")
    join.add_argument("--toolchain-path", help="a toolchain tree this node already owns (hashed by canary)")
    join.add_argument("--idle-only", action="store_true")
    join.add_argument("--cores", type=int)
    join.set_defaults(fn=cmd_join)

    sub.add_parser("leave", help="drop intents and detach").set_defaults(fn=cmd_leave)
    sub.add_parser("status", help="local agent status").set_defaults(fn=cmd_status)

    publish = sub.add_parser("publish", help="plan and publish tasks of one kind from a store snapshot")
    publish.add_argument("kind")
    publish.add_argument("--snapshot", required=True, help="store path (VACUUM INTO copy is made), TU dir, manifest, or sha256:ref")
    publish.add_argument("--basis-hash", help="must equal the snapshot's own basis when the snapshot is a store")
    publish.add_argument("--shard-size", type=int, default=512)
    publish.add_argument("--allow-budget", choices=[b.value for b in BudgetClass if b != BudgetClass.UNBOUNDED], default=BudgetClass.SMALL.value,
                         help="highest budget class a planned task may have (never-awaited rule; default small)")
    publish.add_argument("--option", action="append", metavar="KEY=VALUE", help="planner option (toolchain_identity_hash=..., src=..., passes=a,b)")
    publish.add_argument("--subject", help="partition subject (default: the snapshot's hash)")
    publish.set_defaults(fn=cmd_publish)

    work = sub.add_parser("work", help="step the work loop")
    work.add_argument("--once", action="store_true")
    work.add_argument("--kinds", help="comma-separated kinds to accept (default: every registered kind)")
    work.add_argument("--capability", action="append", help="capability this node claims (normally proven by canary at join)")
    work.set_defaults(fn=cmd_work)

    verify = sub.add_parser("verify", help="step the verifier loop")
    verify.add_argument("--once", action="store_true")
    verify.set_defaults(fn=cmd_verify)

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
    objects_sub.add_parser("gc", help="drop objects no log record references")
    objects.set_defaults(fn=cmd_objects)

    log = sub.add_parser("log", help="per-partition logs")
    log_sub = log.add_subparsers(dest="log_cmd", required=True)
    tail = log_sub.add_parser("tail")
    tail.add_argument("partition")
    tail.add_argument("--since", type=int)
    tail.add_argument("--limit", type=int, default=20)
    log.set_defaults(fn=cmd_log)

    describe = sub.add_parser("describe", help="every registry and adapter")
    describe.add_argument("--verbose", "-v", action="store_true", help="describe() of every item and the assumed names")
    describe.set_defaults(fn=cmd_describe)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
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
