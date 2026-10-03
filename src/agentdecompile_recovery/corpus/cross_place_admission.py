"""Candidate distribution, distinct from recipient acceptance/replacement.

Recorded receipts select an exact source/binary generation; they are not compiler
capabilities. Qualified publication additionally obtains a fresh opaque native
compiler observation and independently checks a narrow physical compatibility
provider. Other source remains discoverable as explicitly unadmitted proposals.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import tempfile
import threading
import weakref
import copy
import time
import subprocess

SCHEMA = 'agentdecompile.cross-place-source/v1'
CANDIDATE_SCHEMA = 'agentdecompile.cross-place-candidate/v1'
PROVIDER = 'pe-x86-signed-int32-noargs-constant-leaf/v1'
AREA = '.cross-place'
_OWNERS = threading.local()
_CHECKED = weakref.WeakKeyDictionary()
_SCHEDULE = weakref.WeakKeyDictionary()
_CACHE = {}
_CACHE_LIMIT = 128
_ATTEMPTS = {}
_ATTEMPT_LIMIT = 128
_RETRY_LIMIT = 2
_RETRY_DELAY = 30.0


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    """Refuse aliases before reading inputs or creating output descendants."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError('symlink_path:' + str(part))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('nonregular_or_hardlinked_input:' + str(path))
    return path


def snapshot(path):
    path = regular(path)
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': digest(raw), 'size': len(raw)}


def unchanged(row):
    return snapshot(row['path']) == row


def read_database(path):
    path = regular(path)
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() or sidecar.is_symlink(): regular(sidecar)
    con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1.0)
    con.row_factory = sqlite3.Row
    return con


class _Rows:
    def __init__(self, rows): self.rows = rows
    def fetchall(self): return list(self.rows)
    def fetchone(self): return self.rows[0] if self.rows else None
    def __iter__(self): return iter(self.rows)


class ObservedRows:
    """Exact bounded SQL observations; after capture no live connection remains.

    SQLite manages shared reader sidecars. This is not a writer reservation or
    a claim that mode=ro never touches shm. All queries share one short snapshot.
    """
    def __init__(self, connection):
        self.connection = connection
        self.rows = {}
        self.count = 0
        self.byte_count = 0
        self.origin = None
    def execute(self, sql, args=()):
        key = (sql, tuple(args))
        if key not in self.rows:
            if self.connection is None: raise ValueError('uncaptured_database_predicate')
            rows = self.connection.execute(sql, args).fetchmany(4097)
            self.count += len(rows)
            self.byte_count += sum(len(canonical(dict(row))) for row in rows)
            if len(rows) > 4096 or self.count > 16384 or self.byte_count > 16 * 1024 * 1024:
                raise ValueError('observation_row_budget_exceeded')
            self.rows[key] = tuple(rows)
        return _Rows(self.rows[key])


@contextmanager
def observe_database(path):
    """Read at most three seconds of selected facts, then release SQLite locks."""
    con = read_database(path)
    deadline = time.monotonic() + 3.0
    con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    observed = ObservedRows(con)
    info = Path(path).stat()
    observed.origin = {'path': str(Path(path).absolute()), 'device': info.st_dev, 'inode': info.st_ino,
        'protocol': 'bounded SQLite shared-reader transaction; captured predicates only'}
    try:
        con.execute('BEGIN')
        con.execute('SELECT count(*) FROM sqlite_schema').fetchone()
        yield observed
    finally:
        observed.connection = None
        con.rollback()
        con.close()


def observe_function(con, bid, addr):
    state = identity_state(con, bid, addr)
    size = state['rows']['function'].get('size')
    if type(size) is int:
        con.execute('SELECT addr,size FROM func WHERE binary_id=? AND addr<>? AND addr<? AND addr+size>?',
                    (bid, addr, addr + size, addr)).fetchall()
    return state


def _row(con, table, where, args):
    rows = con.execute(f'SELECT * FROM {table} WHERE {where}', args).fetchall()
    if len(rows) != 1:
        raise ValueError('missing_or_ambiguous_' + table)
    return dict(rows[0])


def identity_state(con, bid, addr):
    """Fingerprint a bounded complete provenance graph, not a flattened hint."""
    visited, active = {}, set()
    def visit(binary_id, address, depth):
        key = (binary_id, address)
        if key in active: raise ValueError('cyclic_identity_dependencies')
        if key in visited: return visited[key]
        if depth > 8 or len(visited) + len(active) >= 64:
            raise ValueError('unsupported_identity_dependency_closure')
        active.add(key)
        binary = _row(con, 'binary', 'id=?', (binary_id,))
        function = _row(con, 'func', 'binary_id=? AND addr=?', key)
        identity = _row(con, 'identity', 'binary_id=? AND addr=?', key)
        if (not identity.get('logical_id') or not identity.get('method')
                or not identity.get('evidence') or identity.get('confidence') is None):
            raise ValueError('legacy_or_null_identity_provenance')
        try: evidence = json.loads(identity['evidence'])
        except (ValueError, TypeError) as exc: raise ValueError('malformed_identity_evidence') from exc
        if not isinstance(evidence, dict) or evidence.get('quarantine'):
            raise ValueError('quarantined_or_unusable_identity_dependency')
        direct, ancestry = evidence.get('dependencies', []), evidence.get('dependency_ancestry', [])
        if (not isinstance(direct, list) or not isinstance(ancestry, list)
                or any(not isinstance(t, str) for t in direct + ancestry) or len(direct + ancestry) > 64):
            raise ValueError('unsupported_identity_dependencies')
        for token in sorted(set(direct + ancestry)):
            match = re.fullmatch(r'([0-9a-f]{16}):([0-9]+)', token)
            if not match: raise ValueError('unsupported_identity_dependency_token')
            bins = con.execute('SELECT id FROM binary WHERE substr(content_sha256,1,16)=?', (match[1],)).fetchall()
            if len(bins) != 1: raise ValueError('ambiguous_identity_dependency')
            visit(int(bins[0][0]), int(match[2]), depth + 1)
        row = {'binary': binary, 'function': function, 'identity': identity,
               'logical': _row(con, 'logical_function', 'id=?', (identity['logical_id'],))}
        visited[key] = row;active.remove(key)
        return row
    selected = visit(bid, addr, 0)
    state = {**selected, 'dependencies': [visited[k] for k in sorted(visited) if k != (bid, addr)]}
    return {'generation': digest(canonical(state)), 'rows': state}


def physical(con, bid, addr, raw_dir=None, target=None):
    from .source_contribution import pe_region
    state = identity_state(con, bid, addr)
    binary, function = state['rows']['binary'], state['rows']['function']
    slug = binary.get('slug')
    if not isinstance(slug, str) or Path(slug).name != slug or slug in ('.', '..'):
        raise ValueError('unsafe_binary_slug')
    if target is None:
        if raw_dir is None:
            raise ValueError('missing_raw_image_directory')
        target = Path(raw_dir) / slug
    dependency_images = []
    for dependency in state['rows']['dependencies']:
        db = dependency['binary']; ds = db.get('slug')
        if not isinstance(ds, str) or Path(ds).name != ds or ds in ('.', '..'):
            raise ValueError('unsafe_dependency_slug')
        dep = snapshot((Path(raw_dir) if raw_dir is not None else Path(target).parent) / ds)
        if dep['sha256'] != db.get('content_sha256'):
            raise ValueError('dependency_binary_content_changed')
        dependency_images.append(dep)
    image = snapshot(target)
    if not re.fullmatch(r'[0-9a-f]{64}', str(binary.get('content_sha256') or '')):
        raise ValueError('missing_binary_content_identity')
    if image['sha256'] != binary['content_sha256']:
        raise ValueError('binary_content_changed')
    size = function.get('size')
    if type(size) is not int or size <= 0 or function.get('is_thunk'):
        raise ValueError('missing_or_unsupported_function_extent')
    raw = Path(image['path']).read_bytes()
    if digest(raw) != image['sha256']:
        raise ValueError('binary_changed_during_read')
    region = pe_region(raw, addr, size)
    pe = struct.unpack_from('<I', raw, 0x3c)[0]
    directory = pe + 24 + (96 if region['machine'] == 0x14c else 112) + 5 * 8
    if struct.unpack_from('<II', raw, directory) != (0, 0):
        raise ValueError('unsupported_image_relocation_dependencies')
    # The complete declared extent must be unique: reject overlapping entries,
    # even if their prefixes happen to decode as a supported leaf.
    overlaps = con.execute('SELECT addr,size FROM func WHERE binary_id=? AND addr<>? AND addr<? AND addr+size>?',
                          (bid, addr, addr + size, addr)).fetchall()
    if overlaps:
        raise ValueError('overlapping_function_extents')
    return {'binaryId': bid, 'address': addr, 'image': image, 'identity': state,
            'region': region, 'dependencyImages': dependency_images}, raw[region['offset']:region['offset'] + size]


def capture_source_basis(con, bid, addr, source_path, source_bytes, *, raw_dir=None, target=None):
    if not isinstance(con, ObservedRows):
        database = next(row[2] for row in con.execute('PRAGMA database_list') if row[1] == 'main')
        with observe_database(database) as observed:
            observe_function(observed, bid, addr)
        con = observed
    state, _ = physical(con, bid, addr, raw_dir, target)
    source = snapshot(source_path)
    if source['sha256'] != digest(source_bytes):
        raise ValueError('source_changed_during_capture')
    return {'schema': SCHEMA, 'source': source, 'donor': state}


def source_constant(raw):
    text = raw.decode('utf-8')
    # This provider supports a deliberately complete tiny translation unit.
    # No macros, typedefs, pointers, attributes, dependencies or hidden bodies.
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    match = re.fullmatch(r'\s*int\s+([A-Za-z_]\w*)\s*\(\s*void\s*\)\s*\{\s*return\s+(-?(?:0|[1-9][0-9]*))\s*;\s*\}\s*', text)
    if not match or not -(2**31) <= int(match[2]) < 2**31:
        raise ValueError('missing_compatibility_provider_for_source')
    return match[1], int(match[2])


def machine_constant(raw):
    if len(raw) == 6 and raw[0] == 0xb8 and raw[-1] == 0xc3:
        return int.from_bytes(raw[1:5], 'little', signed=True)
    if raw in (b'\x31\xc0\xc3', b'\x33\xc0\xc3'):
        return 0
    raise ValueError('unsupported_complete_leaf_implementation')


@dataclass(frozen=True, eq=False)
class Admission:
    qualified: bool
    reason: str
    evidence: dict


class WorkerCapacity(Exception):
    """Yield without publishing a misleading unadmitted capacity proposal."""


@dataclass(frozen=True)
class ReusedPublication:
    row: dict


def qualify(*, con, source_path, captured, source_bid, address, recipient_bid,
            recipient_address, raw_dir, receipt_row, workspace, db_path, receipt_snapshot=None):
    """One common route for standalone, polling and the bulk compiler hook."""
    donor, donor_code = physical(con, source_bid, address, raw_dir)
    recipient, recipient_code = physical(con, recipient_bid, recipient_address, raw_dir)
    evidence = {'donor': donor, 'recipient': recipient, 'provider': None,
                'databaseObservation': getattr(con, 'origin', None)}
    basis = receipt_row.get('distribution') if isinstance(receipt_row, dict) else None
    if not basis or basis.get('schema') != SCHEMA:
        return Admission(False, 'legacy_or_missing_bound_compile_receipt', evidence)
    if (receipt_row.get('ok') is not True or basis['source'] != snapshot(source_path)
            or basis['source']['sha256'] != digest(captured)):
        return Admission(False, 'stale_source_compile_receipt', evidence)
    if basis['donor'] != donor:
        return Admission(False, 'stale_donor_identity_or_dependency', evidence)
    if donor['identity']['rows']['identity']['logical_id'] != recipient['identity']['rows']['identity']['logical_id']:
        return Admission(False, 'identity_link_changed', evidence)
    symbol, value = source_constant(captured)
    for side in (donor, recipient):
        f = side['identity']['rows']['function']
        if (f.get('return_type') != 'int' or f.get('param_count') != 0
                or f.get('calling_convention') not in ('__cdecl', 'cdecl', '__stdcall', 'stdcall', 'default')
                or f.get('param_types') not in ('[]', '', 'void')):
            return Admission(False, 'missing_or_incompatible_declared_abi', evidence)
    if donor['region']['machine'] != recipient['region']['machine']:
        return Admission(False, 'incompatible_machine_abi', evidence)
    if machine_constant(donor_code) != value or machine_constant(recipient_code) != value:
        return Admission(False, 'incompatible_leaf_implementation', evidence)
    from . import source_contribution as sc
    implementation = snapshot(__file__)
    compiler_profile = sc._toolchain(Path('/usr/bin/clang-22'))
    dependency_profile = [snapshot(m.__file__) for m in (sc, sc.source_claims, sc.verify_recovered_byteexact)]
    cache_key = digest(canonical({'basis': basis, 'receipt': receipt_row, 'selectedReceipt': receipt_snapshot, 'recipient': recipient,
        'implementation': implementation, 'toolchain': compiler_profile, 'dependencies': dependency_profile,
        'databaseObservation': getattr(con, 'origin', None), 'workspaceRoot': str(Path(workspace).absolute())}))
    from .cross_place_checkpoint import Ledger
    lease = getattr(_OWNERS, 'lease', None)
    ledger = Ledger(lease[0]) if lease else None
    if ledger:
        reused = ledger.reused(cache_key)
        if reused is not None: return ReusedPublication(reused)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        try:
            validate_admission(cached)
            return cached
        except ValueError:
            _CACHE.pop(cache_key, None)
    if len(_CACHE) >= _CACHE_LIMIT:
        raise WorkerCapacity('qualification_session_cache_capacity')
    attempt = _ATTEMPTS.get(cache_key)
    if attempt is None:
        if len(_ATTEMPTS) >= _ATTEMPT_LIMIT:
            raise WorkerCapacity('qualification_attempt_capacity_wait_for_new_process')
        attempt = {'count': 0, 'next': 0.0, 'reason': None, 'deterministic': False, 'workspaces': []}
        _ATTEMPTS[cache_key] = attempt
    if attempt['count'] >= _RETRY_LIMIT:
        return Admission(False, attempt['reason'] or 'qualification_attempt_budget_exhausted', evidence)
    if attempt['reason'] and (attempt['deterministic'] or time.monotonic() < attempt['next']):
        return Admission(False, attempt['reason'], evidence)
    # Reserve before allocating. Entries are never evicted during this process:
    # unchanged failures cannot restart a budget via cache churn.
    if ledger:
        reserved, durable = ledger.reserve(cache_key, _RETRY_LIMIT, _RETRY_DELAY)
        if not reserved:
            return Admission(False, durable.get('reason') or 'qualification_attempt_budget_exhausted', evidence)
    attempt['count'] += 1
    owned = None
    try:
        owned = Path(tempfile.mkdtemp(prefix='qualification-', dir=workspace))
        workspace = owned
        if ledger: ledger.outcome(cache_key, workspace=str(owned))
        attempt['workspaces'].append(str(workspace))
        unit = workspace / 'captured.c'
        unit.write_bytes(captured)
        # The opaque producer proves bytes only. Every corpus predicate above
        # belongs to the separately captured read snapshot, never a second DB.
        observation = sc.compile_observation(source=unit, target=donor['image']['path'],
            address=address, size=donor['region']['size'], workspace=workspace,
            compiler='/usr/bin/clang-22', name=symbol, binary_id=source_bid, db=None,
            execution_fds=lease_fds())
        record, produced, error = sc.validate_compile(observation)
        if error or produced != donor_code:
            raise ValueError('fresh_compile_qualification_failed:' + str(error))
        if (Path(source_path).read_bytes() != captured
                or physical(con, source_bid, address, raw_dir)[0] != donor
                or physical(con, recipient_bid, recipient_address, raw_dir)[0] != recipient):
            raise ValueError('inputs_changed_during_qualification')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        deterministic = str(exc) == 'compiler_object_not_raw_equal'
        category = ('incompatible_native_object:' if deterministic else
                    'input_changed_unqualified:' if str(exc) == 'inputs_changed_during_qualification' else
                    'compiler_infrastructure_unqualified:')
        reason = category + str(exc)
        attempt.update(reason=reason, deterministic=deterministic, next=time.monotonic() + _RETRY_DELAY)
        if ledger:
            ledger.outcome(cache_key, state='deterministic' if deterministic else 'failed', reason=reason)
        if owned is not None:
            try:
                (owned / 'attempt.json').write_bytes(canonical({'basis': cache_key, 'attempt': attempt['count'],
                    'reason': reason, 'retryLimit': _RETRY_LIMIT, 'retryDelaySeconds': _RETRY_DELAY,
                    'wake': 'relevant source/receipt/images/provider/toolchain/dependency change or new process'}))
            except OSError:
                # The in-process count/reason remains authoritative even when
                # failing storage cannot retain an additional diagnostic file.
                pass
        return Admission(False, reason, evidence)
    evidence.update(provider={'id': PROVIDER, 'scope': 'signed-int32-return/no-args/no-memory/no-calls',
        'value': value, 'machine': donor['region']['machine'],
        'abi': 'PE scalar int32 in EAX; zero arguments; plain RET',
        'layoutDependencies': [], 'implementationVariant': 'constant-leaf',
        'compilerScope': 'captured-source-and-image-bytes; corpus basis separately observed',
        'compileObservation': record, 'implementation': implementation})
    result = Admission(True, 'qualified_scoped_candidate_requires_recipient_acceptance', evidence)
    _CHECKED[result] = (canonical(evidence), observation)
    _CACHE[cache_key] = result
    if ledger: _SCHEDULE[result] = (ledger, cache_key)
    return result


def validate_admission(result):
    from . import source_contribution as sc
    trusted = _CHECKED.get(result)
    if not trusted or trusted[0] != canonical(result.evidence):
        raise ValueError('untrusted_or_changed_admission')
    provider = result.evidence['provider']
    if not unchanged(provider['implementation']): raise ValueError('provider_implementation_changed')
    _, _, reason = sc.validate_compile(trusted[1])
    if reason: raise ValueError('compile_observation_invalidated:' + reason)
    return True


def stable_evidence(evidence):
    """Ignore only per-attempt identities/paths, preserving every proof field."""
    result = copy.deepcopy(evidence)
    provider = result.get('provider')
    if provider:
        record = provider['compileObservation']
        for key in ('invocation', 'started', 'completed', 'cwd'): record.pop(key)
        paths = {record['snapshot']['path']: '<snapshot>', record['object']['path']: '<object>'}
        record['argv'] = [paths.get(arg, arg) for arg in record['argv']]
        for key in ('source', 'snapshot', 'object'): record[key].pop('path')
        record['candidate'].pop('path')
    return result


def current_retained_evidence(evidence):
    from . import source_contribution as sc
    provider = evidence['provider']
    record = provider['compileObservation']
    entries = [provider['implementation'], record['implementation'], record['source'],
               record['target'], record['snapshot'], record['object'],
               *record['implementationDependencies'], *record['toolchain']]
    if not all(sc.current(entry) for entry in entries):
        raise ValueError('retained_evidence_artifact_changed')
    parsed = sc.parse_coff(Path(record['object']['path']).read_bytes())
    if {k: v for k, v in parsed.items() if k != 'bytes'} != record['coff']:
        raise ValueError('retained_evidence_object_changed')


def lease_fds():
    active = getattr(_OWNERS, 'lease', None)
    return (active[1],) if active else ()


def lease_envelope(out_root):
    from .supervision import process_identity
    active = getattr(_OWNERS, 'lease', None)
    root = Path(out_root).absolute() / AREA
    if not active or active[0] != root: raise ValueError('missing_supervisor_lease')
    info = os.fstat(active[1])
    return {'fd': active[1], 'root': str(root), 'device': info.st_dev,
            'inode': info.st_ino, 'supervisor': process_identity(os.getpid())}


def _held_descriptor(fd, root):
    lock = regular(root / '.owner.lock')
    expected, actual = lock.stat(), os.fstat(fd)
    if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
            or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)):
        raise ValueError('inherited_lease_identity')
    fields = Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines()
    if f'ino:\t{actual.st_ino}' not in fields: raise ValueError('inherited_lease_fdinfo_inode')
    # Btrfs st_dev is a subvolume device, unlike the kernel lock-row device.
    # Association comes from this exact fdinfo; compare inode, not device text.
    # The lock PID can name a reaped original owner. It is NOT liveness evidence.
    locks = [line.split() for line in fields if line.startswith('lock:')]
    if not any(len(row) == 9 and row[2:5] == ['FLOCK', 'ADVISORY', 'WRITE']
               and row[6].rsplit(':', 1)[-1] == str(actual.st_ino)
               and row[7:] == ['0', 'EOF'] for row in locks):
        raise ValueError('inherited_lease_not_preheld')
    return actual


@contextmanager
def borrowed_owner(envelope):
    from .supervision import process_identity
    if getattr(_OWNERS, 'lease', None): raise ValueError('nested_borrowed_lease')
    root = Path(envelope['root']).absolute()
    for p in [root, *root.parents]:
        if p.is_symlink(): raise ValueError('symlink_inherited_scope')
    fd = envelope['fd']
    if type(fd) is not int or fd < 3: raise ValueError('invalid_inherited_fd')
    parent = process_identity(os.getppid())
    expected = envelope['supervisor']
    if (parent.get('identity_unavailable') or expected.get('identity_unavailable')
            or not expected.get('start_ticks')
            or any(parent.get(k) != expected.get(k) for k in ('pid', 'start_ticks', 'boot_id'))):
        raise ValueError('inherited_lease_handoff_parent')
    actual = _held_descriptor(fd, root)
    if (actual.st_dev, actual.st_ino) != (envelope['device'], envelope['inode']):
        raise ValueError('inherited_lease_envelope_identity')
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _held_descriptor(fd, root)
    _OWNERS.lease = (root, fd)
    try: yield root
    finally:
        _OWNERS.lease = None
        os.close(fd)  # Never LOCK_UN a shared open file description.


@contextmanager
def output_owner(out_root, inputs):
    """One cooperating writer across all three routes, for the whole candidate area."""
    root = Path(os.path.abspath(out_root)) / AREA
    for parent in [*reversed(root.parents), root]:
        if parent.is_symlink():
            raise ValueError('symlink_output_path')
    for path in inputs:
        p = Path(os.path.abspath(path))
        if p == root or root in p.parents or p in root.parents:
            raise ValueError('candidate_output_overlaps_input:' + str(p))
    active = getattr(_OWNERS, 'lease', None)
    if active and active[0] == root:
        os.fstat(active[1])  # the outer watch lease remains physically open
        yield root
        return
    if active:
        raise ValueError('nested_candidate_output_scope')
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.owner.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise ValueError('hardlinked_output_lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('candidate_output_owned') from exc
        _OWNERS.lease = (root, fd)
        yield root
    finally:
        _OWNERS.lease = None
        os.close(fd)


def publish(root, captured, transformed, admission, source_path, receipt, check):
    """Atomic directory publication; completeness is the exact source+manifest pair."""
    evidence = admission.evidence
    scheduling = _SCHEDULE.get(admission)
    if admission.qualified: validate_admission(admission)
    state = 'qualified-candidates' if admission.qualified else 'unadmitted-proposals'
    # Stable identity excludes per-attempt compiler timestamps/scratch paths.
    provider = evidence.get('provider')
    key = {'sourceSha256': digest(captured), 'sourcePath': str(source_path),
           'donor': evidence.get('donor'), 'recipient': evidence.get('recipient'),
           'databaseObservation': evidence.get('databaseObservation'),
           'receipt': receipt, 'provider': provider.get('id') if provider else None,
           'qualified': admission.qualified, 'reason': admission.reason,
           'providerBasis': stable_evidence(evidence).get('provider'),
           'transformationSha256': digest(transformed)}
    identifier = digest(canonical(key))
    parent = root / state
    if parent.is_symlink(): raise ValueError('symlink_candidate_area')
    parent.mkdir(exist_ok=True)
    dest = parent / identifier
    manifest = {'schema': CANDIDATE_SCHEMA, 'candidateId': identifier, **key,
                'state': 'requires-recipient-acceptance' if admission.qualified else 'unadmitted',
                'recoveryCredit': False, 'evidence': evidence,
                'observedSnapshot': {'claim': 'observed relevant corpus rows; not current accepted source',
                    'donorGeneration': (evidence.get('donor') or {}).get('identity', {}).get('generation'),
                    'recipientGeneration': (evidence.get('recipient') or {}).get('identity', {}).get('generation'),
                    'currentAcceptance': False, 'database': evidence.get('databaseObservation')},
                'handoff': {'replacementAllowed': False, 'required': [
                    'fresh-source-and-recipient-dependencies', 'recipient-compile',
                    'recipient-ABI-layout-and-behavior', 'target-local-acceptance',
                    'separate-explicit-selection']}}
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or not dest.is_dir(): raise ValueError('candidate_publication_conflict')
        old = json.loads(regular(dest / 'manifest.json').read_text())
        if (regular(dest / 'candidate.c').read_bytes() != transformed or old.get('candidateId') != identifier
                or any(old.get(k) != v for k, v in key.items()) or old.get('schema') != CANDIDATE_SCHEMA
                or old.get('state') != manifest['state'] or old.get('recoveryCredit') is not False
                or old.get('handoff') != manifest['handoff']
                or old.get('observedSnapshot') != manifest['observedSnapshot']):
            raise ValueError('candidate_publication_conflict')
        if admission.qualified:
            try:
                if stable_evidence(old['evidence']) != stable_evidence(evidence):
                    raise ValueError('retained_evidence_mismatch')
                current_retained_evidence(old['evidence'])
            except (OSError, KeyError, TypeError, ValueError) as exc:
                raise ValueError('candidate_publication_conflict:' + str(exc)) from exc
            validate_admission(admission)
        elif old.get('evidence') != evidence:
            raise ValueError('candidate_publication_conflict')
        check()
        if scheduling:
            ledger, key_id = scheduling
            ledger.publication_intent(key_id, dest, (dest / 'manifest.json').read_bytes(), transformed)
            ledger.outcome(key_id, state='published')
        return {'candidate': str(dest), 'published': False, 'qualified': admission.qualified, 'reason': admission.reason}
    staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    try:
        (staging / 'candidate.c').write_bytes(transformed)
        (staging / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
        for p in staging.iterdir():
            with p.open('rb') as f: os.fsync(f.fileno())
        check()
        if admission.qualified: validate_admission(admission)
        if scheduling:
            ledger, key_id = scheduling
            ledger.publication_intent(key_id, dest, (staging / 'manifest.json').read_bytes(), transformed)
        os.rename(staging, dest)
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        if scheduling: ledger.outcome(key_id, state='published')
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return {'candidate': str(dest), 'published': True, 'qualified': admission.qualified, 'reason': admission.reason}
