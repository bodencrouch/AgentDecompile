"""Durable, conservative supervision primitives; no recovery acceptance authority.

The output-root lock coordinates this orchestrator only. It does not establish
ownership of external Ghidra, compiler, Wine, or corpus writers.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class SupervisionError(RuntimeError):
    pass


RESERVED = {"launch_intent", "running", "needs_reconciliation"}
STATES = RESERVED | {"ready", "failed_exit", "pass_done"}


def execution_basis(argv: list[str], provider_revision: str, input_basis: str) -> str:
    """Only explicit inputs/code/arguments; never mutable output or DB metadata."""
    return hashlib.sha256(json.dumps([argv, provider_revision, input_basis],
                                    separators=(",", ":")).encode()).hexdigest()


def provider_revision(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "dashboard" in path.relative_to(root).parts:
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def decide(record: dict, basis: str, now: float, max_failed_exits: int) -> str:
    """Pure admission decision; unknown children retain their reservation."""
    if record.get("state") in RESERVED:
        return "needs_reconciliation"
    if record.get("basis") != basis:
        return "launch"
    if record.get("failed_exits", 0) >= max_failed_exits:
        return "budget_exhausted"
    if now < record.get("next_eligible_at", 0):
        return "cooldown"
    return "launch"


def load_state(path: Path, scope: dict) -> dict:
    if not path.exists():
        return {"version": 1, "scope": scope, "stages": {}}
    try:
        state = json.loads(path.read_text())
        if state["version"] != 1 or state["scope"] != scope or not isinstance(state["stages"], dict):
            raise ValueError("schema or scope mismatch")
        for name, record in state["stages"].items():
            if not isinstance(name, str) or not isinstance(record, dict):
                raise ValueError("invalid stage")
            if record["state"] not in STATES or not isinstance(record["basis"], str):
                raise ValueError("invalid stage state/basis")
            count = record["failed_exits"]
            if type(count) is not int or count < 0:
                raise ValueError("invalid failure count")
            deadline = record["next_eligible_at"]
            if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline < 0:
                raise ValueError("invalid cooldown")
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SupervisionError(f"supervision state unreadable/invalid; refusing admission: {exc}") from exc


def save_state(path: Path, state: dict) -> None:
    """Replace plus fsync file and directory before any dispatch is permitted."""
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def owner_lock(directory: Path):
    try:
        import fcntl
    except ImportError as exc:
        raise SupervisionError("dispatch requires POSIX flock support; use --status for read-only inspection on this host") from exc
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "owner.lock").open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SupervisionError("another orchestrator owns this output root") from exc
        yield


def process_identity(pid: int) -> dict:
    """Diagnostic identity only, never permission to kill or adopt a process."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": stat[19],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return {"pid": pid, "identity_unavailable": True}


def session_clearance(identity: dict, proc_root: Path = Path("/proc")) -> str:
    """Check the admitted Linux session after its leader was reaped.

    Signal-free observation never kills/adopts a PID. Unreadable membership or
    missing original identity is unknown. This covers session descendants, not
    external writers or children deliberately escaping into a new session.
    """
    if identity.get("identity_unavailable") or not identity.get("start_ticks"):
        return "unknown"
    try:
        if (proc_root / "sys/kernel/random/boot_id").read_text().strip() != identity.get("boot_id"):
            return "unknown"
        entries = list(proc_root.iterdir())
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                # pgrp and session are fields 5 and 6 (state is index zero).
                if int(fields[2]) == identity["pid"] or int(fields[3]) == identity["pid"]:
                    return "occupied"
            except FileNotFoundError:
                continue  # unrelated processes may exit during enumeration
        return "clear"
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return "unknown"


def _resource_observer_read(path, limit):
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('process_metadata_limit')
    return value


def _resource_observer_path(value):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        return None
    return str(Path(value).resolve())


def _resource_observer_entries(directory, limit, numeric=False):
    entries = []
    for entry in directory.iterdir():
        if numeric and not entry.name.isdigit():
            continue
        entries.append(entry)
        if len(entries) > limit:
            raise ValueError('process_or_descriptor_inventory_limit')
    return entries


def _resource_observer_kernel_path(value):
    # /proc cwd/fd links expose kernel paths, not source symlink spellings.
    # Do not stat/resolve every descriptor target (possibly slow mounted media).
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        return None
    return os.path.normpath(value)


def _resource_paths_overlap(left, right):
    a, b = Path(left), Path(right)
    return a == b or a in b.parents or b in a.parents


def _compiler_resource_use(scope, process):
    """Pure current-use classification; no historical ownership authority."""
    result = {'compiler': 'clear', 'winePrefix': 'clear',
              'outputs': ['clear'] * len(scope['outputRoots']), 'reasons': []}
    if process.get('candidate') is None or not process.get('identityStable'):
        return {**result, 'compiler': 'unknown', 'winePrefix': 'unknown',
                'outputs': ['unknown'] * len(scope['outputRoots']),
                'reasons': ['process_classification_or_identity_unavailable']}
    if process.get('candidate') is False:
        return result
    prefix = process.get('winePrefix')
    same_namespace = process.get('sameMountNamespace')
    if not same_namespace:
        result.update(compiler='unknown', winePrefix='unknown',
                      outputs=['unknown'] * len(scope['outputRoots']))
        result['reasons'].append('process_mount_namespace_unqualified')
        return result
    if not process.get('environmentComplete') or not prefix:
        result.update(compiler='unknown', winePrefix='unknown')
        result['reasons'].append('explicit_process_wine_prefix_unavailable')
    elif prefix == scope['winePrefix']:
        result.update(compiler='occupied', winePrefix='occupied')
    else:
        # Different path spellings are not a physical disjointness proof:
        # bind mounts may alias one prefix even in the same mount namespace.
        # Do not stat arbitrary mounted media to turn this snapshot into a
        # potentially unbounded filesystem probe.
        result.update(compiler='unknown', winePrefix='unknown')
        result['reasons'].append('physical_prefix_disjointness_unqualified')
    paths = process.get('openPaths', [])
    cwd = process.get('cwd')
    if cwd:
        paths = paths + [cwd]
    for index, output in enumerate(scope['outputRoots']):
        if any(_resource_paths_overlap(output, path) for path in paths):
            result['outputs'][index] = 'occupied'
        elif not process.get('cwdComplete') or not process.get('openPathsComplete'):
            result['outputs'][index] = 'unknown'
            result['reasons'].append('scoped_process_output_paths_unavailable')
        else:
            result['outputs'][index] = 'unknown'
            result['reasons'].append('physical_output_disjointness_unqualified')
    return result


def observe_compiler_resources(scope):
    """Bounded read-only snapshot of current compiler/Wine process use.

    The caller supplies the actual adapter configuration (vcRoot, winePrefix,
    outputRoots); no environment/default selection or historical reconstruction
    occurs here. ``clear`` means no use observed by the covered process classes,
    NOT safe admission: unrelated writers, escaped/provider work, races after
    observation and cooperating leases require independent qualification.
    No raw arguments, environment, cwd or descriptor paths leave this observer.
    """
    import time
    limits = {'processes': 16384, 'metadataBytes': 1048576,
              'descriptorsPerProcess': 4096, 'totalDescriptors': 131072,
              'occupantPreview': 64, 'outputRoots': 64}
    started = time.time()
    if not isinstance(scope, dict):
        raise ValueError('compiler resource scope must be a mapping')
    outputs = scope.get('outputRoots', [])
    if not isinstance(outputs, (list, tuple)) or len(outputs) > limits['outputRoots']:
        raise ValueError('invalid or excessive output roots')
    canonical = {'vcRoot': _resource_observer_path(scope.get('vcRoot')),
                 'winePrefix': _resource_observer_path(scope.get('winePrefix')),
                 'outputRoots': [_resource_observer_path(value) for value in outputs]}
    if not canonical['vcRoot'] or not canonical['winePrefix'] or any(value is None for value in canonical['outputRoots']):
        raise ValueError('compiler scope requires explicit absolute dependency paths')
    canonical['outputRoots'] = sorted(set(canonical['outputRoots']))
    domains = {'compiler': {'state': 'clear', 'path': canonical['vcRoot'], 'occupiedCount': 0, 'unknownCount': 0},
               'winePrefix': {'state': 'clear', 'path': canonical['winePrefix'], 'occupiedCount': 0, 'unknownCount': 0},
               'outputs': [{'state': 'clear', 'path': path, 'occupiedCount': 0, 'unknownCount': 0}
                           for path in canonical['outputRoots']]}
    coverage = {'enumerated': 0, 'classified': 0, 'notCompilerClass': 0,
                'disappeared': 0, 'candidateProcesses': 0, 'descriptors': 0,
                'inventoryStable': False, 'inventoryComplete': False,
                'metadataComplete': False, 'complete': False,
                'classificationAtomic': False,
                'completeSemantics': 'bounded enumeration and metadata coverage, not an atomic process-class snapshot'}
    reasons = {}
    occupants = []
    boot = machine = namespace = None
    root = Path('/proc')
    def reason(name):
        reasons[name] = reasons.get(name, 0) + 1
    def apply(use, identity):
        entries = [(domains['compiler'], use['compiler']), (domains['winePrefix'], use['winePrefix'])]
        entries.extend(zip(domains['outputs'], use['outputs']))
        relevant = False
        for entry, state in entries:
            if state == 'occupied':
                entry['occupiedCount'] += 1
                entry['state'] = 'occupied'
                relevant = True
            elif state == 'unknown':
                entry['unknownCount'] += 1
                if entry['state'] != 'occupied':
                    entry['state'] = 'unknown'
        for name in set(use['reasons']):
            reason(name)
        if relevant and len(occupants) < limits['occupantPreview']:
            occupants.append({'identity': identity, 'compiler': use['compiler'],
                              'winePrefix': use['winePrefix'],
                              'outputIndices': [i for i, state in enumerate(use['outputs']) if state == 'occupied']})
    try:
        boot = _resource_observer_read(root / 'sys/kernel/random/boot_id', 128).decode('ascii').strip()
        machine = _resource_observer_read(Path('/etc/machine-id'), 128).decode('ascii').strip()
        namespace = os.readlink(root / 'self/ns/mnt')
        if not boot or not machine:
            raise ValueError('host_identity_unavailable')
        initial = sorted(_resource_observer_entries(root, limits['processes'], numeric=True), key=lambda entry: int(entry.name))
        coverage['enumerated'] = len(initial)
        for entry in initial:
            pid = int(entry.name)
            process = {'candidate': None, 'identityStable': False, 'sameMountNamespace': False,
                       'environmentComplete': False, 'cwdComplete': False,
                       'openPathsComplete': False, 'openPaths': []}
            identity = {'pid': pid, 'boot_id': boot}
            try:
                stat_text = _resource_observer_read(entry / 'stat', 16384).decode('utf-8')
                stat = stat_text.rsplit(')', 1)[1].split()
                if len(stat) < 20:
                    raise ValueError('process_stat_incomplete')
                identity['start_ticks'] = stat[19]
                if stat[0] in {'Z', 'X'}:
                    checked = _resource_observer_read(entry / 'stat', 16384).decode('utf-8').rsplit(')', 1)[1].split()
                    if len(checked) < 20 or checked[19] != identity['start_ticks'] or checked[0] not in {'Z', 'X'}:
                        raise ValueError('process_identity_changed')
                    coverage['notCompilerClass'] += 1
                    continue
                command = _resource_observer_read(entry / 'cmdline', limits['metadataBytes']).decode('utf-8', errors='strict').split('\0')
                names = [token.replace('\\', '/').rsplit('/', 1)[-1].lower() for token in command if token]
                names.append(stat_text.partition('(')[2].rsplit(')', 1)[0].lower())
                try:
                    names.append(os.readlink(entry / 'exe').rsplit('/', 1)[-1].lower())
                except OSError:
                    pass  # Candidate metadata below still fails closed.
                compiler_names = {'wine', 'wine64', 'wine-preloader', 'wine64-preloader',
                                  'wineserver', 'wineserver64', 'cl.exe', 'link.exe'}
                adapter_names = {'compiler_msvc71.py', 'agentdecompile_recovery.corpus.compiler_msvc71',
                                 'agentdecompile_recovery.corpus.text_permuter_watch'}
                process['candidate'] = (bool(set(names).intersection(compiler_names | adapter_names))
                                        or any(name.endswith('.exe') for name in names)) if any(names) else None
                coverage['classified'] += 1
                if process['candidate'] is False:
                    process['candidate'] = None  # Revalidation failure must not retain an exclusion.
                    checked = _resource_observer_read(entry / 'stat', 16384).decode('utf-8').rsplit(')', 1)[1].split()
                    if len(checked) < 20 or checked[19] != identity['start_ticks']:
                        process['candidate'] = None
                        raise ValueError('process_identity_changed')
                    coverage['notCompilerClass'] += 1
                    continue
                coverage['candidateProcesses'] += 1
                try:
                    process['sameMountNamespace'] = os.readlink(entry / 'ns/mnt') == namespace
                    environment = _resource_observer_read(entry / 'environ', limits['metadataBytes']).decode('utf-8', errors='strict').split('\0')
                    env = dict(item.split('=', 1) for item in environment if '=' in item)
                    prefix_values = {item.split('=', 1)[1] for item in environment if item.startswith('WINEPREFIX=')}
                    if len(prefix_values) > 1:
                        raise ValueError('ambiguous_process_wine_prefix')
                    process['winePrefix'] = _resource_observer_path(env.get('WINEPREFIX'))
                    process['environmentComplete'] = True
                except (OSError, ValueError, UnicodeError):
                    reason('candidate_environment_or_namespace_unavailable')
                try:
                    process['cwd'] = _resource_observer_kernel_path(os.readlink(entry / 'cwd'))
                    process['cwdComplete'] = process['cwd'] is not None
                except (OSError, ValueError):
                    reason('candidate_cwd_unavailable')
                if canonical['outputRoots']:
                    try:
                        budget = min(limits['descriptorsPerProcess'],
                                     max(0, limits['totalDescriptors'] - coverage['descriptors']))
                        descriptors = _resource_observer_entries(entry / 'fd', budget)
                        coverage['descriptors'] += len(descriptors)
                        if coverage['descriptors'] > limits['totalDescriptors']:
                            raise ValueError('descriptor_inventory_limit')
                        for descriptor in descriptors:
                            path = _resource_observer_kernel_path(os.readlink(descriptor))
                            if path:
                                process['openPaths'].append(path)
                        process['openPathsComplete'] = True
                    except (OSError, ValueError):
                        reason('candidate_descriptors_unavailable')
                else:
                    process['openPathsComplete'] = True
                final_stat = _resource_observer_read(entry / 'stat', 16384).decode('utf-8').rsplit(')', 1)[1].split()
                process['identityStable'] = len(final_stat) >= 20 and final_stat[19] == identity['start_ticks']
            except FileNotFoundError:
                coverage['disappeared'] += 1
                continue
            except (OSError, ValueError, UnicodeError, IndexError):
                reason('process_metadata_unavailable')
            apply(_compiler_resource_use(canonical, process), identity)
        final = {entry.name for entry in _resource_observer_entries(root, limits['processes'], numeric=True)}
        coverage['inventoryStable'] = final == {entry.name for entry in initial}
        final_boot = _resource_observer_read(root / 'sys/kernel/random/boot_id', 128).decode('ascii').strip()
        coverage['inventoryComplete'] = coverage['inventoryStable'] and final_boot == boot and not coverage['disappeared']
        coverage['metadataComplete'] = not reasons
        coverage['complete'] = coverage['inventoryComplete'] and coverage['metadataComplete']
        if not coverage['inventoryComplete']:
            reason('process_inventory_changed_during_observation')
            apply({'compiler': 'unknown', 'winePrefix': 'unknown',
                   'outputs': ['unknown'] * len(canonical['outputRoots']), 'reasons': []}, {})
    except (OSError, ValueError, UnicodeError):
        reason('host_or_process_inventory_unavailable')
        apply({'compiler': 'unknown', 'winePrefix': 'unknown',
               'outputs': ['unknown'] * len(canonical['outputRoots']), 'reasons': []}, {})
    return {'source': 'current-local-compiler-resource-observer-v1',
            'observedAt': started, 'completedAt': time.time(),
            'host': {'machineId': machine, 'bootId': boot}, 'dependencies': domains,
            'coverage': coverage, 'limits': limits, 'reasonCounts': reasons,
            'occupants': occupants, 'clearanceQualified': False,
            'historicalOwnershipResolved': False, 'admissionAuthorized': False,
            'limitations': ['Current compiler-class process-use snapshot, not a held resource lease',
                            'Other writers, detached/remote provider operations and future opens are not ruled out',
                            'Same-PID exec/classification races are not excluded by start-time revalidation',
                            'Different prefix paths need independent physical-disjointness qualification',
                            'Nonoverlapping output path spellings do not rule out bind-mount aliases',
                            'No prefix daemon completion or historical attempt/host binding',
                            'A clear observed domain is not permission to release a reservation']}
