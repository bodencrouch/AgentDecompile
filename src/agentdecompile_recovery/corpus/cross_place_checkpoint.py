"""Durable cross-place scheduling facts, never compiler/admission authority.

Every entry is bounded and addressed by its full relevant-basis digest. The
candidate owner serializes updates; reservations precede all scratch allocation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

SCHEMA = "cross-place-checkpoint/v1"
MAX_RECORD = 2 * 1024 * 1024
_DURABLE_DIRECTORIES = {}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def directory(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink(): raise ValueError("checkpoint_symlink")
    for part in [*reversed(path.parents), path]:
        if not part.exists(): part.mkdir()
        if not part.is_dir(): raise ValueError("checkpoint_parent_not_directory")
        info = part.stat(); identity = (info.st_dev, info.st_ino)
        if _DURABLE_DIRECTORIES.get(str(part)) == identity: continue
        # Publish a cache fact only after BOTH barriers succeed. A failed
        # first mkdir/parent-fsync therefore cannot be skipped on retry.
        for target in (part, part.parent):
            fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        if len(_DURABLE_DIRECTORIES) < 4096:
            _DURABLE_DIRECTORIES[str(part)] = identity
    return path


def sync_directory(path):
    """Persist newly changed entries; ancestor-initialization cache is irrelevant."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def read(path):
    from .cross_place_admission import regular
    path = regular(path)
    if path.stat().st_size > MAX_RECORD: raise ValueError("checkpoint_record_budget")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict): raise ValueError("checkpoint_record_shape")
    return value


def save(path, value):
    path = Path(path)
    directory(path.parent)
    if path.exists() or path.is_symlink(): read(path)
    raw = canonical(value)
    if len(raw) > MAX_RECORD: raise ValueError("checkpoint_record_budget")
    fd, temporary = tempfile.mkstemp(prefix=".commit-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class Ledger:
    def __init__(self, area):
        self.area = directory(area)
        self.root = directory(self.area / "checkpoint")
        info = self.area.stat()
        self.scope = {"schema": SCHEMA, "area": str(self.area),
                      "device": info.st_dev, "inode": info.st_ino}
        path = self.root / "scope.json"
        if path.exists():
            if read(path) != self.scope: raise ValueError("checkpoint_scope_changed")
        else: save(path, self.scope)

    def path(self, key):
        if not re.fullmatch(r"[0-9a-f]{64}", key): raise ValueError("checkpoint_key")
        return directory(self.root / "entries" / key[:2]) / (key + ".json")

    def get(self, key):
        path = self.path(key)
        if not path.exists(): return None
        row = read(path)
        if (row.get("schema") != SCHEMA or row.get("key") != key
                or row.get("scope") != self.scope or type(row.get("count")) is not int
                or not 0 <= row["count"] <= 2):
            raise ValueError("checkpoint_entry_corrupt")
        if row.get('state') not in {'reserved', 'failed', 'deterministic', 'publishing', 'published', 'interrupted'}:
            raise ValueError('checkpoint_entry_state')
        if row['count'] < 1: raise ValueError('checkpoint_entry_count')
        for name in ('reservedAt', 'notBefore', 'monotonic'):
            value = row.get(name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('checkpoint_entry_deadline')
        if row['notBefore'] < row['reservedAt']: raise ValueError('checkpoint_entry_deadline')
        if row['state'] in ('publishing', 'published'):
            pub = row.get('publication')
            if (not isinstance(pub, dict) or not isinstance(pub.get('path'), str)
                    or any(not re.fullmatch(r'[0-9a-f]{64}', str(pub.get(k, '')))
                           for k in ('manifestSha256', 'candidateSha256'))):
                raise ValueError('checkpoint_publication_shape')
        return row

    def put(self, key, row):
        save(self.path(key), {**row, "schema": SCHEMA, "key": key, "scope": self.scope})

    def reserve(self, key, limit=2, delay=30.0):
        row = self.get(key) or {"count": 0, "state": "new"}
        now = time.time()
        if row["state"] in ("published", "publishing", "deterministic"):
            return False, row
        if row["count"] >= limit:
            return False, row
        # Wall time rollback never grants a fresh attempt. A reservation whose
        # process died consumes its count and retains its original deadline.
        if now < row.get("reservedAt", 0) or now < row.get("notBefore", 0):
            return False, row
        row.update(count=row["count"] + 1, state="reserved", reservedAt=now,
                   notBefore=now + delay, reason="interrupted_reserved_attempt",
                   boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                   monotonic=time.monotonic())
        self.put(key, row)
        return True, row

    def outcome(self, key, **changes):
        row = self.get(key)
        if row is None: raise ValueError("checkpoint_missing_reservation")
        row.update(changes); self.put(key, row)

    def publication_intent(self, key, destination, manifest, candidate):
        destination = Path(destination)
        if destination.parent.parent != self.area: raise ValueError("publication_scope")
        self.outcome(key, state="publishing", publication={
            "path": str(destination), "manifestSha256": hashlib.sha256(manifest).hexdigest(),
            "candidateSha256": hashlib.sha256(candidate).hexdigest()})

    def reused(self, key):
        from . import cross_place_admission as gate
        row = self.get(key)
        if not row or row["state"] not in ("published", "publishing"): return None
        pub = row.get("publication", {})
        path = Path(pub.get("path", ""))
        if path.parent != self.area / "qualified-candidates": raise ValueError("checkpoint_publication_scope")
        if not path.exists():
            # Intent before rename without a publication cannot assert success.
            # It spent the reserved attempt; retain that budget for finite retry.
            self.outcome(key, state="interrupted", reason="publication_not_committed")
            return None
        raw = gate.regular(path / "manifest.json").read_bytes()
        candidate = gate.regular(path / "candidate.c").read_bytes()
        if (hashlib.sha256(raw).hexdigest() != pub.get("manifestSha256")
                or hashlib.sha256(candidate).hexdigest() != pub.get("candidateSha256")):
            raise ValueError("checkpoint_publication_changed")
        manifest = json.loads(raw)
        if (manifest.get("schema") != gate.CANDIDATE_SCHEMA or manifest.get("qualified") is not True
                or manifest.get("recoveryCredit") is not False
                or manifest.get("candidateId") != path.name):
            raise ValueError("checkpoint_publication_invalid")
        gate.current_retained_evidence(manifest["evidence"])
        if row["state"] != "published": self.outcome(key, state="published")
        return {"candidate": str(path), "published": False, "qualified": True,
                "reason": "reused-publication", "evidenceState": "reused-historical-publication",
                "currentAcceptance": False}



def binding_path(path):
    """The one spelling of a binding path, identical to admission.snapshot()."""
    return os.path.abspath(path)


def binding_name(source, receipt):
    """Latest-slot name. append() and finish_append() must agree exactly."""
    return digest({'source': binding_path(source), 'receipt': binding_path(receipt)})


def publication_child(root, path):
    """Canonical journal write scope, with traversal and symlinks refused."""
    root = Path(root).absolute(); path = Path(path).absolute()
    if '..' in root.parts or '..' in path.parts:
        raise ValueError('publication_parent_traversal')
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('publication_symlink')
    root = root.resolve(); path = path.resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('publication_outside_scope')
    return path


class PublicationIndex:
    """Producer publication journal, separate from the candidate writer lease.

    Index entries are discoverable scheduling inputs. Their source/receipt bytes
    are always freshly captured by admission; an event grants no qualification.
    """
    def __init__(self, out):
        self.out = Path(out).absolute()
        if '..' in self.out.parts: raise ValueError('publication_parent_traversal')
        directory(self.out)
        self.out = self.out.resolve()
        self.root = directory(self.out / '.source-publications')
        self.meta = self.root / 'index.json'

    def locked(self):
        from contextlib import contextmanager
        import fcntl
        @contextmanager
        def enter():
            import threading
            active = getattr(self, '_active_lock', None)
            if active and active[0] == threading.get_ident():
                os.fstat(active[1]); yield self; return
            fd = os.open(self.root / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                if os.fstat(fd).st_nlink != 1: raise ValueError('publication_lock_alias')
                deadline = time.monotonic() + 3
                while True:
                    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                    except BlockingIOError:
                        if time.monotonic() >= deadline: raise ValueError('publication_index_busy_retry')
                        time.sleep(.01)
                if not self.meta.exists(): save(self.meta, {'schema': SCHEMA, 'sequence': 0, 'pending': None})
                self.recover()
                self._active_lock = (threading.get_ident(), fd)
                yield self
            finally:
                self._active_lock = None
                os.close(fd)
        return enter()

    def state(self):
        row = read(self.meta)
        if (row.get('schema') != SCHEMA or type(row.get('sequence')) is not int
                or row['sequence'] < 0): raise ValueError('publication_index_corrupt')
        return row

    def event_path(self, sequence):
        return directory(self.root / 'events' / str(sequence // 1000)) / f'{sequence:016d}.json'

    def append(self, source, receipt):
        from .cross_place_admission import snapshot
        self.finish_append()
        binding = {'source': snapshot(source), 'receipt': snapshot(receipt) if Path(receipt).exists() else {'path': binding_path(receipt), 'unavailable': True}}
        # Name the slot from the recorded paths, never from the caller's
        # spelling: a '..' binding would otherwise strand appendPending.
        name = binding_name(binding['source']['path'], binding['receipt']['path'])
        latest = directory(self.root / 'latest' / name[:2]) / (name + '.json')
        if latest.exists() and read(latest).get('binding') == binding: return
        row = self.state(); seq = row['sequence'] + 1
        event = {'schema': SCHEMA, 'sequence': seq, 'binding': binding}
        row['appendPending'] = {'event': event, 'latest': str(latest)}
        save(self.meta, row)
        self.finish_append()

    def finish_append(self):
        row = self.state(); pending = row.get('appendPending')
        if not pending: return
        event = pending['event']; seq = event['sequence']
        if type(seq) is not int or seq <= 0: raise ValueError('append_intent_sequence')
        latest = publication_child(self.root / 'latest', pending['latest'])
        name = binding_name(event['binding']['source']['path'],
                            event['binding']['receipt']['path'])
        if latest != self.root / 'latest' / name[:2] / (name + '.json'):
            raise ValueError('append_intent_scope')
        if seq not in (row['sequence'], row['sequence'] + 1): raise ValueError('append_intent_sequence')
        path = self.event_path(seq)
        if path.exists() and read(path) != event: raise ValueError('publication_sequence_conflict')
        save(path, event)
        row['sequence'] = seq; save(self.meta, row)
        save(latest, {'binding': event['binding'], 'sequence': seq})
        row['appendPending'] = None; save(self.meta, row)

    def recover(self):
        from .cross_place_admission import snapshot, regular
        self.finish_append()
        row = self.state(); pending = row.get('pending')
        if not pending: return
        selected = []
        # Validate every target/staging scope before replaying the first file.
        # A malformed later entry is not an interrupted legitimate publication.
        for entry in pending['files']:
            path = publication_child(self.out, entry['path'])
            if self.root == path or self.root in path.parents:
                raise ValueError('publication_intent_scope')
            if path.exists(): regular(path)
            staged = publication_child(self.root, entry['staged'])
            if staged.parent.parent != self.root or not staged.parent.name.startswith('publication-'):
                raise ValueError('publication_staging_scope')
            selected.append((entry, path, regular(staged)))
        bindings = self.bindings(pending.get('bindings'))
        for entry, path, staged in selected:
            current = snapshot(path) if path.exists() else None
            if current not in (entry['before'], entry['after']):
                raise ValueError('publication_intent_external_conflict')
            raw = staged.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry['after']['sha256']:
                raise ValueError('publication_intent_staging_changed')
            if current != entry['after']:
                directory(path.parent)
                fd, temp = tempfile.mkstemp(prefix='.source-publication-', dir=path.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                    os.replace(temp, path)
                finally:
                    if os.path.exists(temp): os.unlink(temp)
            # A prior attempt may have replaced successfully then failed its
            # barrier. Matching new bytes never proves that barrier completed.
            sync_directory(path.parent)
        for source, receipt in bindings:
            self.append(source, receipt)
        row = self.state(); row['pending'] = None; save(self.meta, row)

    def bindings(self, bindings):
        """Validate every binding before durable intent or before any replay.

        A receipt has the same write scope as a published file (inside out,
        no symlink, outside the journal). A source is canonical and outside
        the journal. Returns canonical string pairs.
        """
        if not isinstance(bindings, (list, tuple)): raise ValueError('publication_binding_shape')
        checked = []
        for pair in bindings:
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or not all(isinstance(p, (str, os.PathLike)) for p in pair)):
                raise ValueError('publication_binding_shape')
            source = Path(binding_path(pair[0])); receipt = Path(binding_path(pair[1]))
            if self.root == source or self.root in source.parents:
                raise ValueError('publication_binding_scope')
            try: receipt = publication_child(self.out, receipt)
            except ValueError: raise ValueError('publication_binding_scope') from None
            if self.root == receipt or self.root in receipt.parents:
                raise ValueError('publication_binding_scope')
            checked.append((str(source), str(receipt)))
        return checked

    def publish(self, files, bindings):
        """Caller holds index lock. Durable intent covers every source/receipt rename."""
        from .cross_place_admission import snapshot
        selected = []
        for path, raw in files:
            path = publication_child(self.out, path)
            if self.root == path or self.root in path.parents:
                raise ValueError('publication_intent_scope')
            selected.append((path, raw))
        published = {path for path, _ in selected}
        bindings = self.bindings(list(bindings))
        # A binding source this publication does not write must be enrollable
        # now; otherwise recover() would fail on it after the intent is durable.
        for source, _ in bindings:
            if Path(source) not in published: snapshot(source)
        stage = Path(tempfile.mkdtemp(prefix='publication-', dir=self.root))
        directory(stage)
        entries = []
        for number, (path, raw) in enumerate(selected):
            before = snapshot(path) if path.exists() else None
            staged = stage / str(number)
            with staged.open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            entries.append({'path': str(path), 'before': before,
                'after': {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)},
                'staged': str(staged)})
        sync_directory(stage)
        row = self.state()
        row['pending'] = {'files': entries, 'bindings': [list(pair) for pair in bindings]}
        save(self.meta, row)
        self.recover()

    def bootstrap(self, source, receipt, cancel=None):
        """Complete bounded membership capture, with adaptive managed retry.

        No mutable-directory cookie survives a lock release or crash. Existing
        registrations keep running while an import is incomplete. Large stable
        trees grow the next capture budget; explicit immutable imports bypass
        directory enumeration entirely.
        """
        source = Path(source).absolute(); receipt = Path(receipt).absolute()
        key = digest({'source': str(source), 'receipt': str(receipt)})
        progress = self.root / ('bootstrap-' + key + '.json')
        prior = read(progress) if progress.exists() else {'budget': 4096, 'timeBudget': 3.0}
        with self.locked():
            before = source.stat()
            revision = [before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns]
            if prior.get('revision') == revision and prior.get('complete'): return prior
            budget = prior['budget']; time_budget = prior.get('timeBudget', 3.0); names = []; started = time.monotonic()
            with os.scandir(source) as iterator:
                for item in iterator:
                    if cancel and cancel.is_set(): raise InterruptedError('bootstrap_cancelled')
                    if len(names) >= budget or time.monotonic() - started > time_budget:
                        state = {'budget': budget * 2, 'timeBudget': time_budget * 2, 'complete': False,
                                 'reason': 'bootstrap_incomplete_requires_managed_capture_or_immutable_import',
                                 'observedEntries': len(names), 'seconds': time.monotonic()-started}
                        save(progress, state); return state
                    names.append(item.name)
            after = source.stat()
            if revision != [after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns]:
                state = {'budget': budget, 'complete': False, 'reason': 'external_membership_changed_during_bootstrap'}
                save(progress, state); return state
        # Immutable inventory contains names only. Per-entry stable source and
        # selected receipt snapshots are captured when importing each chunk.
        names = sorted(name for name in names if name.endswith('.c') and not name.startswith('_'))
        chunks = []
        for offset in range(0, len(names), 128):
            if cancel and cancel.is_set(): raise InterruptedError('bootstrap_cancelled')
            chunk = {'names': names[offset:offset+128]}
            identifier = digest(chunk)
            chunk_path = self.root / ('members-' + identifier + '.json')
            save(chunk_path, chunk)
            chunks.append({'path': str(chunk_path), 'sha256': identifier, 'count': len(chunk['names'])})
        inventory = {'schema': SCHEMA, 'source': str(source), 'sourceIdentity': revision[:2],
                     'receipt': str(receipt), 'chunks': chunks, 'count': len(names)}
        raw = canonical(inventory)
        identifier = hashlib.sha256(raw).hexdigest()
        manifest = self.root / ('inventory-' + identifier + '.json')
        save(manifest, inventory)
        state = {'budget': budget, 'timeBudget': time_budget, 'complete': True, 'revision': revision,
                 'manifest': str(manifest), 'sha256': identifier, 'cursor': 0}
        save(progress, state)
        return state

    def import_manifest(self, manifest, expected_hash, cursor=0, limit=128, *, expected_source=None):
        """Restartable bounded import of exact immutable root-bound membership."""
        from .cross_place_admission import regular
        raw = regular(manifest).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash: raise ValueError('import_manifest_changed')
        inventory = json.loads(raw)
        source = Path(inventory['source']).absolute()
        info = source.stat()
        scope_matches = source == Path(expected_source).absolute() if expected_source is not None else self.out in source.parents
        if (not scope_matches or any(p.is_symlink() for p in (source, *source.parents))
                or inventory.get('schema') != SCHEMA
                or [info.st_dev, info.st_ino] != inventory['sourceIdentity']):
            raise ValueError('import_manifest_scope')
        chunks = inventory['chunks']
        if not isinstance(chunks, list) or len(chunks) > 8192: raise ValueError('import_manifest_budget')
        if type(cursor) is not int or not 0 <= cursor <= len(chunks): raise ValueError('import_cursor')
        if cursor == len(chunks): return cursor, len(chunks)
        chunk = chunks[cursor]
        path = regular(chunk['path'])
        if path.parent != self.root: raise ValueError('import_chunk_scope')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != chunk['sha256']: raise ValueError('import_chunk_changed')
        names = json.loads(raw)['names']
        if len(names) != chunk['count'] or len(names) > limit: raise ValueError('import_chunk_budget')
        for name in names:
            if not isinstance(name, str) or Path(name).name != name or not name.endswith('.c'):
                raise ValueError('import_manifest_entry')
            path = source / name
            if path.exists(): self.append(path, inventory['receipt'])
        return cursor + 1, len(chunks)



class Scan:
    def __init__(self, ledger, source, parameters):
        self.ledger = ledger
        self.source = Path(source).absolute()
        info = self.source.stat()
        scope = {'source': str(self.source), 'device': info.st_dev, 'inode': info.st_ino,
                 'parameters': parameters}
        self.index = PublicationIndex(ledger.area.parent)
        self.path = ledger.root / 'scan.json'
        if self.path.exists():
            self.row = read(self.path)
            if self.row.get('scope') != scope or self.row.get('schema') != SCHEMA:
                raise ValueError('scan_scope_changed')
        else:
            self.row = {'schema': SCHEMA, 'scope': scope, 'epoch': 0, 'frontier': 0,
                        'inventory': [], 'cursor': None, 'sealed': False, 'highwater': 0}
            save(self.path, self.row)

    def enroll(self, cancel=None):
        state = self.index.bootstrap(self.source, self.row['scope']['parameters']['receipt'], cancel)
        # An explicit root-bound immutable manifest is also a supported import
        # route. It supplies scheduling membership only, never acceptance.
        managed = self.index.root / ('managed-' + digest(str(self.source)) + '.json')
        if managed.exists():
            supplied = read(managed)
            state = {**state, 'manifest': supplied['manifest'], 'sha256': supplied['sha256']}
        if state.get('manifest'):
            manifest = Path(state['manifest'])
            progress = self.ledger.root / ('import-' + state['sha256'] + '.json')
            old = read(progress) if progress.exists() else {'cursor': 0}
            with self.index.locked():
                cursor, total = self.index.import_manifest(manifest, state['sha256'], old['cursor'], expected_source=self.source)
            save(progress, {'manifest': str(manifest), 'sha256': state['sha256'], 'cursor': cursor, 'total': total})
            state['importComplete'] = cursor == total
        self.row['bootstrap'] = state
        save(self.path, self.row)

    def seal(self):
        if self.row['sealed']: return
        with self.index.locked():
            if self.row['frontier'] >= self.row['highwater']:
                self.row.update(epoch=self.row['epoch'] + 1, frontier=0,
                                highwater=self.index.state()['sequence'])
            start = self.row['frontier'] + 1
            stop = min(self.row['highwater'], start + 127)
            names = []
            for sequence in range(start, stop + 1):
                event = read(self.index.event_path(sequence))
                if (event.get('schema') != SCHEMA or event.get('sequence') != sequence
                        or not isinstance(event.get('binding'), dict)):
                    raise ValueError('publication_event_corrupt')
                source = Path(event['binding']['source']['path'])
                if source.parent == self.source:
                    names.append((source.name, event['binding']['receipt']['path']))
            names = sorted(set(names))
            self.row.update(inventory=names, inventoryDigest=digest(names), cursor=None,
                            sealed=True, nextFrontier=stop)
            save(self.path, self.row)

    def pending(self):
        self.seal()
        if digest(self.row['inventory']) != self.row['inventoryDigest']: raise ValueError('scan_inventory_changed')
        cursor = self.row['cursor']
        return [(self.source / item[0], item[1]) for item in self.row['inventory']
                if cursor is None or tuple(item) >= tuple(cursor[:2])]

    def set_context(self, receipt):
        self.receipt = str(receipt)

    def progress(self, source, recipient=None):
        self.row['cursor'] = [Path(source).name, self.receipt, list(recipient) if recipient is not None else None]
        save(self.path, self.row)

    def skip(self, source, recipient=None):
        cursor = self.row['cursor']
        if cursor is None: return False
        key = (Path(source).name, self.receipt)
        if key < tuple(cursor[:2]): return True
        if key > tuple(cursor[:2]): return False
        return cursor[2] is None or (recipient is not None and tuple(recipient) <= tuple(cursor[2]))

    def finish(self):
        self.row.update(sealed=False, inventory=[], cursor=None, frontier=self.row['nextFrontier'])
        save(self.path, self.row)


def publish_receipt(out, path, value):
    """Durable receipt publication plus current per-source enrollment, including refusals."""
    index = PublicationIndex(out)
    bindings = []
    for row in value.get('results', []):
        if not isinstance(row, dict): continue
        source = ((row.get('distribution') or {}).get('source') or {}).get('path') or row.get('sourcePath')
        if source and Path(source).is_file(): bindings.append((source, str(path)))
    with index.locked():
        index.publish([(path, canonical(value) + b'\n')], bindings)


class ResultReport:
    """Bounded row transport for observations, never acceptance or clearance.

    Only the current generation and current aggregate are retained. Each exact
    byte sequence is bound to its generation and hash before it is consumed.
    Large public reports expose a complete JSONL artifact and an explicit page.
    """
    COUNTERS = ('placed', 'proposed', 'idempotent', 'skipped_no_addr')

    def __init__(self, ledger, kind, token):
        if kind not in ('worker', 'aggregate'): raise ValueError('report_kind')
        self.root = directory(ledger.root / 'reports')
        self.path = self.root / (kind + '-results.jsonl')
        self.pending = self.root / (kind + '-results.pending')
        self.token = token
        self.counts = dict.fromkeys(self.COUNTERS, 0)
        self.rows = 0; self.inline = []; self.inline_size = 0; self.inline_closed = False
        from . import cross_place_admission as gate
        for path in (self.pending, self.path):
            if path.exists() or path.is_symlink(): gate.regular(path)
        self.stream = self.pending.open('wb')
        self.hash = hashlib.sha256(); self.size = 0
        self._write({'schema': 'cross-place-result/v1', 'token': token,
                     'area': str(ledger.area), 'kind': kind})

    def _write(self, value):
        raw = canonical(value) + b'\n'
        if len(raw) > MAX_RECORD: raise ValueError('report_row_too_large')
        self.stream.write(raw); self.hash.update(raw); self.size += len(raw)

    def add(self, row, category=None):
        if category is not None and category not in self.COUNTERS: raise ValueError('report_counter')
        if row is not None and not isinstance(row, dict): raise ValueError('report_row')
        try: self._write({'row': row, 'counter': category})
        except (OSError, ValueError) as exc:
            # A failed report must abort the generation, not be converted by
            # place_tree into an ordinary refused source and skip its cursor.
            raise RuntimeError('generation_report_write_failed') from exc
        if category: self.counts[category] += 1
        if row is not None:
            self.rows += 1
            size = len(canonical(row))
            if not self.inline_closed and len(self.inline) < 128 and self.inline_size + size <= 128 * 1024:
                self.inline.append(row); self.inline_size += size
            else: self.inline_closed = True

    def finish(self):
        self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
        os.replace(self.pending, self.path)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return {**self.counts, 'results': self.inline,
                'resultsTruncated': len(self.inline) != self.rows, 'resultCount': self.rows,
                'completeResults': {'path': str(self.path), 'sha256': self.hash.hexdigest(),
                                    'size': self.size, 'token': self.token}}

    def close(self):
        self.stream.close()


def consume_report(ledger, summary, token, sink=None):
    """Validate the entire completed worker artifact before trusting its counts."""
    from . import cross_place_admission as gate
    info = summary['completeResults']
    expected = ledger.root / 'reports/worker-results.jsonl'
    if info.get('path') != str(expected) or info.get('token') != token:
        raise ValueError('report_scope_changed')
    path = gate.regular(expected)
    hasher = hashlib.sha256(); size = 0; counts = dict.fromkeys(ResultReport.COUNTERS, 0); rows = 0
    inline = []; inline_size = 0; inline_closed = False
    with path.open('rb') as stream:
        header_raw = stream.readline(MAX_RECORD + 1)
        if len(header_raw) > MAX_RECORD or not header_raw.endswith(b'\n'):
            raise ValueError('report_header_too_large')
        header = json.loads(header_raw)
        if header != {'schema': 'cross-place-result/v1', 'token': token,
                      'area': str(ledger.area), 'kind': 'worker'}:
            raise ValueError('report_header_changed')
        hasher.update(header_raw); size += len(header_raw)
        while raw := stream.readline(MAX_RECORD + 1):
            if len(raw) > MAX_RECORD or not raw.endswith(b'\n'): raise ValueError('report_row_too_large')
            entry = json.loads(raw); row = entry['row']; category = entry['counter']
            if row is not None and not isinstance(row, dict): raise ValueError('report_row')
            if category is not None and category not in counts: raise ValueError('report_counter')
            if category: counts[category] += 1
            if row is not None:
                rows += 1; row_size = len(canonical(row))
                if not inline_closed and len(inline) < 128 and inline_size + row_size <= 128 * 1024:
                    inline.append(row); inline_size += row_size
                else: inline_closed = True
            hasher.update(raw); size += len(raw)
    if (hasher.hexdigest() != info.get('sha256') or size != info.get('size')
            or rows != summary.get('resultCount') or any(summary.get(k) != v for k, v in counts.items())
            or summary.get('results') != inline or summary.get('resultsTruncated') is not (len(inline) != rows)):
        raise ValueError('report_content_changed')
    if sink:
        # Complete integrity validation precedes any destination mutation. The
        # parent holds the exclusive output lease and the writer session is
        # already clear; no cooperating generation can change this artifact.
        with path.open('rb') as stream:
            stream.readline(MAX_RECORD + 1)
            while raw := stream.readline(MAX_RECORD + 1):
                if len(raw) > MAX_RECORD: raise ValueError('report_row_too_large')
                entry = json.loads(raw); sink(entry['row'], entry['counter'])
    return counts
