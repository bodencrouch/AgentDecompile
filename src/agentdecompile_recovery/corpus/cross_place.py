"""Distribute separate recipient candidates; never select or replace source."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import subprocess
import threading
import uuid
from contextlib import ExitStack

from . import cross_place_admission as admission

ADDR_RE = re.compile(r'address:\s*0x([0-9a-fA-F]+)', re.I)
_UNRESOLVED_LEASES = []
SKIP_SLUG_SUFFIX = ('.keep',)
_BOOTSTRAP = ('import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv.pop(1));'
              'from agentdecompile_recovery.corpus.cross_place import guarded_main;guarded_main(sys.argv[1])')


def program_id(repo_path):
    return (repo_path or '').rstrip('/').split('/')[-1]


def safe_stem(name, entry_hex):
    return (re.sub(r'[^A-Za-z_0-9]+', '_', name or f'FUN_{entry_hex}').strip('_') or f'FUN_{entry_hex}')[:80]


def parse_addr(text):
    matches = ADDR_RE.findall(text[:800])
    return int(matches[0], 16) if len(matches) == 1 else None


def rewrite_for_dest(text, dst_hex, dst_program, src_hex):
    # Preserve every donor byte after a diagnostic header. Removing an arbitrary
    # first comment could remove real pre-comment code, preprocessor directives,
    # or part of the translation unit. Address transformation is header-only.
    safe_program = safe_stem(dst_program, dst_hex)
    banner = (f'/* cross-place candidate for {safe_program}; recipient-address: 0x{dst_hex}; '
              f'from 0x{src_hex}; requires recipient acceptance; no recovery credit. */\n')
    return banner + text


def should_write(dest, src_is_asm):
    """Compatibility helper: distribution never overwrites an existing file."""
    return not Path(dest).exists() and not Path(dest).is_symlink()


def load_index(con, src_bid, source_address=None):
    out = {}
    predicate = ' AND i1.addr=?' if source_address is not None else ''
    args = (src_bid, source_address) if source_address is not None else (src_bid,)
    rows = con.execute('''SELECT i1.addr AS src_addr,i2.binary_id AS dst_bid,i2.addr AS dst_addr,
        b.slug,b.repo_path,COALESCE(f.name,'') AS dst_name FROM identity i1
        JOIN identity i2 ON i2.logical_id=i1.logical_id AND i2.binary_id<>i1.binary_id
        JOIN binary b ON b.id=i2.binary_id LEFT JOIN func f ON f.binary_id=i2.binary_id AND f.addr=i2.addr
        WHERE i1.binary_id=?''' + predicate + ' ORDER BY i1.addr,i2.binary_id,i2.addr', args)
    for row in rows:
        if str(row['slug'] or '').endswith(SKIP_SLUG_SUFFIX): continue
        out.setdefault(int(row['src_addr']), []).append((int(row['dst_bid']), int(row['dst_addr']),
            program_id(str(row['repo_path'] or '')), str(row['dst_name'] or '')))
    return out


def resolve_source_dir(out_dir, program):
    if not isinstance(program, str) or Path(program).name != program or program in ('.', '..'):
        raise ValueError('unsafe_source_program')
    for path in [out_dir / program, out_dir / 'dump-source/verified',
                 out_dir / 'dump-source/advisory/ghidra', out_dir / 'dump-source/Port/CODE', out_dir / 'dump-source']:
        if path.is_dir() and any(path.glob('*.c')): return path
    return None


def selected_source(params):
    """An explicit caller root is a contract, never a basename search hint."""
    path = (Path(params['source-dir']).absolute() if params.get('source-dir')
            else resolve_source_dir(Path(params['out-dir']), params['from']))
    if path is None: return None
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('symlink_source_directory')
    if not path.is_dir(): raise ValueError('source_directory_unavailable')
    return path.resolve(strict=True)


def _receipt(path):
    if path is None: return None, {}, 'missing_compile_receipt'
    try:
        captured = admission.snapshot(path)
        data = json.loads(Path(path).read_bytes())
        if admission.snapshot(path) != captured: raise ValueError('receipt_changed_during_read')
        return captured, data, None
    except (OSError, ValueError, TypeError) as exc:
        return None, {}, 'unusable_compile_receipt:' + str(exc)


def _receipt_row(data, source, address):
    rows = data.get('results', []) if isinstance(data, dict) else []
    matches = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict): continue
            basis = row.get('distribution') or {}
            if (basis.get('source', {}).get('path') == str(source)
                    and basis.get('donor', {}).get('address') == address): matches.append(row)
    return matches[0] if len(matches) == 1 else {}


def _db_path(con):
    rows = con.execute('PRAGMA database_list').fetchall()
    path = next((row[2] for row in rows if row[1] == 'main'), '')
    if not path: raise ValueError('cross_place_requires_file_database')
    return Path(path).resolve()


def place_one(src_path, src_addr, index, out_root, *, con=None, src_bid=None,
              raw_dir=None, receipt_path=None, no_compile_gate=False):
    """Legacy address-only callers refuse; all real routes pass current context."""
    if con is None or src_bid is None:
        return 0
    result = place_tree(Path(src_path).parent, src_bid, out_root, con, raw_dir=raw_dir,
        receipt_path=receipt_path, no_compile_gate=no_compile_gate, source_paths=[Path(src_path)])
    return result['placed']


def place_tree(src_dir, src_bid, out_root, con, *, raw_dir=None, receipt_path=None,
               no_compile_gate=False, source_paths=None, compile_ok=None, scan=None, result_sink=None):
    """Refresh source, receipt and index on every pass; address sets never admit."""
    if con is None:
        return {'placed': 0, 'proposed': 0, 'reason': 'missing_live_identity_database', 'results': []}
    database = admission.regular(_db_path(con))
    src_dir, out_root = Path(src_dir).absolute(), Path(out_root).absolute()
    receipt_path = Path(receipt_path) if receipt_path else out_root / 'compile-receipt.json'
    paths = sorted(source_paths if source_paths is not None else src_dir.glob('*.c'))
    sidecars = [Path(str(database) + suffix) for suffix in ('-wal', '-shm', '-journal')]
    for path in sidecars:
        if path.exists() or path.is_symlink(): admission.regular(path)
    inputs = [database, *sidecars, *paths, receipt_path]
    if raw_dir:
        # Files, not the raw directory's parent: out/.cross-place can coexist
        # with out/extract/raw but may not contain any actual image input.
        inputs.extend(Path(raw_dir).glob('*'))
    stats = {'placed': 0, 'proposed': 0, 'idempotent': 0, 'skipped_no_addr': 0, 'results': []}
    with admission.output_owner(out_root, inputs) as area:
        for path in paths:
            if path.name.startswith('_') or (scan and scan.skip(path)): continue
            try:
                path = admission.regular(path)
                captured = path.read_bytes()
                source_snapshot = admission.snapshot(path)
                if source_snapshot['sha256'] != admission.digest(captured): raise ValueError('source_changed_during_capture')
                text = captured.decode('utf-8')
                addr = parse_addr(text)
                if addr is None:
                    stats['skipped_no_addr'] += 1
                    if result_sink: result_sink(None, 'skipped_no_addr')
                    if scan: scan.progress(path)
                    continue
                # No cached index/receipt can authorize a later source event.
                # Materialize bounded relevant SQL facts in one short transaction.
                # No reader/DB exclusion survives into native compile or sleep.
                with admission.observe_database(database) as observed_rows:
                    index = load_index(observed_rows, src_bid, addr)
                    for selected_bid, selected_addr in [(src_bid, addr),
                            *[(b, a) for b, a, _, _ in index.get(addr, [])]]:
                        try: admission.observe_function(observed_rows, selected_bid, selected_addr)
                        except (ValueError, TypeError, KeyError): pass
                receipt, data, receipt_error = _receipt(receipt_path)
                selected = _receipt_row(data, path, addr)
                for bid, dst_addr, program, name in index.get(addr, []):
                    if scan and scan.skip(path, (bid, dst_addr)): continue
                    evidence = {'databaseObservation': observed_rows.origin,
                                'donor': {'binaryId': src_bid, 'address': addr},
                                'recipient': {'binaryId': bid, 'address': dst_addr}, 'provider': None}
                    observed = None
                    try:
                        # Even refused proposals carry current identity generations
                        # when available; this never upgrades their claim.
                        donor, _ = admission.physical(observed_rows, src_bid, addr, raw_dir)
                        recipient, _ = admission.physical(observed_rows, bid, dst_addr, raw_dir)
                        evidence.update(donor=donor, recipient=recipient)
                        observed = (donor, recipient)
                        if no_compile_gate:
                            result = admission.Admission(False, 'explicit_unadmitted_exploration', evidence)
                        elif receipt_error:
                            result = admission.Admission(False, receipt_error, evidence)
                        else:
                            retained = area / 'producer-evidence'
                            if retained.is_symlink(): raise ValueError('symlink_producer_evidence')
                            retained.mkdir(exist_ok=True)
                            workspace = retained
                            result = admission.qualify(con=observed_rows, source_path=path, captured=captured,
                                source_bid=src_bid, address=addr, recipient_bid=bid, recipient_address=dst_addr,
                                raw_dir=raw_dir, receipt_row=selected, workspace=workspace, db_path=database,
                                receipt_snapshot=receipt)
                    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                        result = admission.Admission(False, str(exc), evidence)
                    # Transformation only adds a comment; the captured TU is intact.
                    transformed = rewrite_for_dest(text, f'{dst_addr:08x}', program, f'{addr:08x}').encode()
                    def check():
                        if admission.snapshot(path) != source_snapshot:
                            raise ValueError('source_changed_before_publication')
                        if receipt and admission.snapshot(receipt_path) != receipt:
                            raise ValueError('receipt_changed_before_publication')
                        # Corpus rows are immutable captured facts. External files
                        # remain checked; recipient acceptance must resolve a fresh
                        # corpus basis and cannot assume atomic DB-to-rename freshness.
                        if observed and (admission.physical(observed_rows, src_bid, addr, raw_dir)[0],
                                         admission.physical(observed_rows, bid, dst_addr, raw_dir)[0]) != observed:
                            raise ValueError('identity_or_image_changed_before_publication')
                    check()
                    if isinstance(result, admission.ReusedPublication):
                        row = result.row
                    else:
                        row = admission.publish(area, captured, transformed, result, path, receipt, check)
                    if scan: scan.progress(path, (bid, dst_addr))
                    category = ('placed' if row['qualified'] else 'proposed') if row['published'] else 'idempotent'
                    stats[category] += 1
                    if result_sink: result_sink(row, category)
                    else: stats['results'].append(row)
                if scan: scan.progress(path)
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                row = {'source': str(path), 'published': False, 'qualified': False, 'reason': str(exc)}
                if result_sink: result_sink(row, None)
                else: stats['results'].append(row)
                if scan: scan.progress(path)
    return stats


def watch(src_dir, src_bid, out_root, con, interval, *, raw_dir=None, receipt_path=None, no_compile_gate=False):
    if interval <= 0: raise ValueError('watch_interval_must_be_positive')
    repo = con.execute('SELECT repo_path FROM binary WHERE id=?', (src_bid,)).fetchone()[0]
    params = {'from': Path(src_dir).name, 'repo': repo, 'db': str(_db_path(con)),
              'source-dir': str(Path(src_dir).absolute()),
              'out-dir': str(Path(out_root).absolute()), 'raw-dir': str(Path(raw_dir).absolute()),
              'byteexact-receipt': str(receipt_path or Path(out_root) / 'compile-receipt.json'),
              'watch': True, 'interval': interval, 'no-compile-gate': no_compile_gate}
    return supervise(params)


def _watch_wait(interval, cancel):
    """Interrupt a watch delay without spawning another worker generation."""
    return cancel.wait(interval)


def _standalone_execute(argv, fds, cancel, on_started=None):
    from .supervision import process_identity, session_clearance
    from ..native_verify_contract import clean_environment
    import queue
    import signal
    import time
    if cancel.is_set(): return 1, '[cancelled before spawn]'
    proc = subprocess.Popen(argv, env=clean_environment(), pass_fds=fds,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)
    identity = {}
    lines = queue.Queue(maxsize=128)
    stopped = threading.Event()
    def drain():
        try:
            descriptor = proc.stdout.fileno()
            os.set_blocking(descriptor, False)
            while not stopped.is_set():
                try:
                    raw = os.read(descriptor, 4096)
                except BlockingIOError:
                    stopped.wait(.05)
                    continue
                if not raw: break
                line = raw.decode('utf-8', errors='replace')
                while not stopped.is_set():
                    try: lines.put(line, timeout=.1); break
                    except queue.Full: pass
                if stopped.is_set(): return
        except (OSError, ValueError):
            pass
        finally:
            try: lines.put(None, timeout=.1)
            except queue.Full: pass
    reader = None
    output = ''; eof = False; cancellation = None; exited = None
    deadline = time.monotonic() + 1800
    try:
        identity = process_identity(proc.pid)
        if on_started: on_started(identity)
        reader = threading.Thread(target=drain, daemon=True,
                                  name=f'agentdecompile-standalone-output-{proc.pid}')
        reader.start()
        while True:
            now = time.monotonic()
            if (cancel.is_set() or now >= deadline) and cancellation is None:
                cancellation = now
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            if cancellation is not None and now - cancellation >= 5:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                if now - cancellation >= 7: break
            if proc.poll() is not None:
                exited = exited or now
                if eof or now - exited >= 2: break
            try:
                line = lines.get(timeout=.1)
                if line is None: eof = True
                else: output = (output + line)[-2 * 1024 * 1024:]
            except queue.Empty: pass
        try: code = proc.wait(timeout=2)
        except subprocess.TimeoutExpired: code = None
        if code is None or session_clearance(identity) != 'clear':
            raise ValueError('ownership remains unresolved: standalone worker session')
        return (1 if cancellation is not None else code), output
    except BaseException:
        # Protect the spawn-to-owner-persistence window as well as execution.
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired: pass
        if session_clearance(identity) != 'clear':
            _UNRESOLVED_LEASES.extend(os.dup(fd) for fd in fds)
        raise
    finally:
        stopped.set()
        if reader is not None and reader.ident is not None:
            reader.join(timeout=.5)
        proc.stdout.close()



def supervise(params, *, execute=None, transition=None, cancel=None, aggregate=False):
    """Lifetime flock parent; each native generation has a fresh bounded cache."""
    from .cross_place_checkpoint import Ledger, Scan, ResultReport, consume_report, save, read
    cancel = cancel or threading.Event()
    standalone = execute is None
    out = Path(params['out-dir'])
    with ExitStack() as cleanup, admission.output_owner(out, [Path(params['db']), Path(params['raw-dir']),
            Path(params['byteexact-receipt'])]) as area:
        ledger = Ledger(area)
        execution_path = ledger.root / 'standalone-execution.json'
        if standalone:
            from .supervision import session_clearance
            if execution_path.exists():
                previous = read(execution_path)
                if previous.get('implementation') != _implementation():
                    raise ValueError('standalone_restoration_implementation_changed')
                if previous.get('phase') == 'dispatch-possible' and (
                        not previous.get('owner') or session_clearance(previous['owner']) != 'clear'):
                    raise ValueError('ownership remains unresolved: prior standalone generation')
            def execute(argv, fds, event):
                def started(identity):
                    record = read(execution_path); record['owner'] = identity
                    save(execution_path, record)
                return _standalone_execute(argv, fds, event, on_started=started)
        src = selected_source(params)
        if src is None: raise ValueError('no_source_directory')
        scan = Scan(ledger, src, {'repo': params['repo'], 'db': params['db'],
                    'raw': params['raw-dir'], 'receipt': params['byteexact-receipt'],
                    'exploration': bool(params.get('no-compile-gate'))})
        report = ResultReport(ledger, 'aggregate', uuid.uuid4().hex) if aggregate else None
        if report: cleanup.callback(report.close)
        # One-shot completes a finite sealed sweep; watch starts later epochs.
        while not cancel.is_set():
            scan.enroll(cancel)
            scan.seal()
            if not scan.row['inventory'] and not scan.row.get('bootstrap', {}).get('importComplete'):
                print(json.dumps({'event': 'cross-place-bootstrap', **scan.row.get('bootstrap', {})}),
                      file=sys.stderr if aggregate else sys.stdout, flush=True)
                scan.finish()
                if cancel.wait(min(8.0, float(params.get('interval', 8)))): break
                continue
            envelope = {'version': 1, 'generation': uuid.uuid4().hex,
                        'lease': admission.lease_envelope(out),
                        'scanDigest': admission.digest(scan.path.read_bytes())}
            argv = guarded_command(params, envelope)
            if standalone:
                save(execution_path, {'phase': 'intent', 'generation': envelope['generation'],
                    'implementation': _implementation(), 'argv': argv, 'owner': None})
            if transition: transition('intent', argv, envelope)
            if cancel.is_set():
                if transition: transition('undispatched', argv, envelope)
                break
            if transition: transition('dispatch', argv, envelope)
            if standalone:
                record = read(execution_path); record['phase'] = 'dispatch-possible'
                save(execution_path, record)
            code, log = execute(argv, admission.lease_fds(), cancel)
            if transition: transition('cleared', argv, envelope)
            if standalone:
                record = read(execution_path); record['phase'] = 'cleared'
                save(execution_path, record)
            if code not in (0, 75):
                if report: report.close()
                if log: print(log, end='' if log.endswith('\n') else '\n', flush=True)
                return code, log
            frames = [json.loads(line) for line in log.splitlines() if line.startswith('{')]
            frame = next((item for item in reversed(frames)
                          if item.get('event') == 'cross-place-generation'
                          and item.get('generation') == envelope['generation']), None)
            if frame is None: raise ValueError('missing_generation_report')
            consume_report(ledger, frame['report'], envelope['generation'], report.add if report else None)
            if not aggregate:
                print(json.dumps({**frame['report'], 'generation': envelope['generation'],
                                  'status': frame['status']}, sort_keys=True), flush=True)
            # Reload state committed by this cleared worker. Child JSON never
            # substitutes for the caller's actual whole-session observer.
            scan = Scan(ledger, src, scan.row['scope']['parameters'])
            if code == 75:
                if not scan.row['sealed']: raise ValueError('capacity_without_pending_epoch')
                continue
            if scan.row['sealed']: raise ValueError('worker_did_not_finish_epoch')
            if (scan.row['frontier'] >= scan.row['highwater']
                    and scan.row.get('bootstrap', {}).get('importComplete')):
                if not params.get('watch'):
                    if report: print(json.dumps(report.finish(), sort_keys=True), flush=True)
                    return 0, log
                interval = float(params.get('interval', 8))
                if interval <= 0: raise ValueError('watch_interval_must_be_positive')
                _watch_wait(interval, cancel)
        if report: report.close()
        return 1, '[cancelled]'


def worker(params, envelope):
    from .cross_place_checkpoint import Ledger, Scan, ResultReport
    with admission.borrowed_owner(envelope['lease']) as area:
        ledger = Ledger(area)
        src = selected_source(params)
        scan = Scan(ledger, src, {'repo': params['repo'], 'db': params['db'],
                    'raw': params['raw-dir'], 'receipt': params['byteexact-receipt'],
                    'exploration': bool(params.get('no-compile-gate'))})
        if admission.digest(scan.path.read_bytes()) != envelope['scanDigest']:
            raise ValueError('worker_scan_intent_changed')
        with admission.read_database(params['db']) as con:
            from .propagate import bid
            source_binary_id = bid(con, params['repo'])
            report = ResultReport(ledger, 'worker', envelope['generation'])
            try:
                for source, receipt in scan.pending():
                    scan.set_context(receipt)
                    place_tree(src, source_binary_id, params['out-dir'], con,
                        raw_dir=params['raw-dir'], receipt_path=receipt,
                        no_compile_gate=bool(params.get('no-compile-gate')),
                        source_paths=[source], scan=scan, result_sink=report.add)
            except admission.WorkerCapacity:
                print(json.dumps({'event': 'cross-place-generation', 'status': 'capacity',
                                  'generation': envelope['generation'], 'epoch': scan.row['epoch'],
                                  'report': report.finish()}), flush=True)
                return 75
            except BaseException:
                report.close()
                raise
        scan.finish()
        print(json.dumps({'event': 'cross-place-generation', 'status': 'complete',
                          'generation': envelope['generation'], 'report': report.finish()}, sort_keys=True), flush=True)
        return 0


def freeze_parameters(params, root):
    result = dict(params)
    for name in ('db', 'out-dir', 'raw-dir'):
        if not result.get(name): raise ValueError('cross_place_requires_' + name)
        p = Path(result[name]);result[name] = str((p if p.is_absolute() else root / p).absolute())
    if result.get('source-dir'):
        source = Path(result['source-dir'])
        result['source-dir'] = str((source if source.is_absolute() else root / source).absolute())
    p = Path(result.get('byteexact-receipt') or Path(result['out-dir']) / 'compile-receipt.json')
    # Internal normalized source receipt includes the implicit default.
    result['byteexact-receipt'] = str((p if p.is_absolute() else root / p).absolute())
    admission.regular(result['db'])
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(result['db'] + suffix)
        if sidecar.exists() or sidecar.is_symlink(): admission.regular(sidecar)
    for name in ('out-dir', 'raw-dir', 'byteexact-receipt'):
        for part in [Path(result[name]), *Path(result[name]).parents]:
            if part.is_symlink(): raise ValueError('symlink_cross_place_resource')
    return result


def _implementation():
    from . import source_contribution, cross_place_checkpoint
    return {str(Path(p).resolve()): admission.digest(Path(p).read_bytes()) for p in
            (__file__, admission.__file__, source_contribution.__file__, cross_place_checkpoint.__file__)}


def guarded_command(params, generation=None):
    root = str(Path(__file__).resolve().parents[2])
    return [sys.executable, '-I', '-S', '-c', _BOOTSTRAP, root, json.dumps({'params': params, 'implementation': _implementation(), **({'generation': generation} if generation else {})}, sort_keys=True)]


def command_matches(argv, params):
    try:
        payload = json.loads(argv[-1])
        generation = payload.get('generation')
        if generation and (generation.get('version') != 1 or not generation.get('generation')): return False
        return argv == guarded_command(params, generation)
    except (TypeError, ValueError, IndexError, AttributeError): return False


def guarded_main(raw):
    payload = json.loads(raw)
    if payload['implementation'] != _implementation(): raise ValueError('cross_place_implementation_changed')
    params = payload['params']
    if payload.get('generation'):
        raise SystemExit(worker(params, payload['generation']))
    args = ['--from', params['from'], '--db', params['db'], '--out-dir', params['out-dir'],
            '--repo', params['repo'], '--raw-dir', params['raw-dir'], '--byteexact-receipt', params['byteexact-receipt']]
    if params.get('watch'): args += ['--watch', '--interval', str(params.get('interval', 8))]
    if params.get('no-compile-gate'): args += ['--no-compile-gate']
    if params.get('source-dir'): args += ['--source-dir', params['source-dir']]
    raise SystemExit(main(args))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='program', required=True)
    ap.add_argument('--db', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--raw-dir', type=Path, required=True)
    ap.add_argument('--source-dir', type=Path)
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--interval', type=float, default=8.0)
    ap.add_argument('--byteexact-receipt', type=Path)
    ap.add_argument('--no-compile-gate', action='store_true')
    args = ap.parse_args(argv)
    params = freeze_parameters({'from': args.program, 'db': str(args.db), 'out-dir': str(args.out_dir),
        'repo': args.repo, 'raw-dir': str(args.raw_dir), 'byteexact-receipt': str(args.byteexact_receipt) if args.byteexact_receipt else None,
        'source-dir': str(args.source_dir.absolute()) if args.source_dir else None,
        'watch': args.watch, 'interval': args.interval, 'no-compile-gate': args.no_compile_gate}, Path.cwd())
    return supervise(params, aggregate=not args.watch)[0]



if __name__ == '__main__':
    raise SystemExit(main())
