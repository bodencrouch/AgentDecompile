"""Distribute separate recipient candidates; never select or replace source."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from time import sleep as _watch_wait

from . import cross_place_admission as admission

ADDR_RE = re.compile(r'address:\s*0x([0-9a-fA-F]+)', re.I)
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


def load_index(con, src_bid):
    out = {}
    rows = con.execute('''SELECT i1.addr AS src_addr,i2.binary_id AS dst_bid,i2.addr AS dst_addr,
        b.slug,b.repo_path,COALESCE(f.name,'') AS dst_name FROM identity i1
        JOIN identity i2 ON i2.logical_id=i1.logical_id AND i2.binary_id<>i1.binary_id
        JOIN binary b ON b.id=i2.binary_id LEFT JOIN func f ON f.binary_id=i2.binary_id AND f.addr=i2.addr
        WHERE i1.binary_id=? ORDER BY i1.addr,i2.binary_id,i2.addr''', (src_bid,))
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
               no_compile_gate=False, source_paths=None, compile_ok=None):
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
            if path.name.startswith('_'): continue
            try:
                path = admission.regular(path)
                captured = path.read_bytes()
                source_snapshot = admission.snapshot(path)
                if source_snapshot['sha256'] != admission.digest(captured): raise ValueError('source_changed_during_capture')
                text = captured.decode('utf-8')
                addr = parse_addr(text)
                if addr is None:
                    stats['skipped_no_addr'] += 1
                    continue
                # No cached index/receipt can authorize a later source event.
                # Materialize bounded relevant SQL facts in one short transaction.
                # No reader/DB exclusion survives into native compile or sleep.
                with admission.observe_database(database) as observed_rows:
                    index = load_index(observed_rows, src_bid)
                    for selected_bid, selected_addr in [(src_bid, addr),
                            *[(b, a) for b, a, _, _ in index.get(addr, [])]]:
                        try: admission.observe_function(observed_rows, selected_bid, selected_addr)
                        except (ValueError, TypeError, KeyError): pass
                receipt, data, receipt_error = _receipt(receipt_path)
                selected = _receipt_row(data, path, addr)
                for bid, dst_addr, program, name in index.get(addr, []):
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
                                raw_dir=raw_dir, receipt_row=selected, workspace=workspace, db_path=database)
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
                    row = admission.publish(area, captured, transformed, result, path, receipt, check)
                    stats['results'].append(row)
                    if row['published']: stats['placed' if row['qualified'] else 'proposed'] += 1
                    else: stats['idempotent'] += 1
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                stats['results'].append({'source': str(path), 'published': False, 'qualified': False, 'reason': str(exc)})
    return stats


def watch(src_dir, src_bid, out_root, con, interval, *, raw_dir=None, receipt_path=None, no_compile_gate=False):
    if interval <= 0: raise ValueError('watch_interval_must_be_positive')
    # Keep the writer lease across polls and waits. Nested per-pass checks reuse
    # only this thread's still-open lease; separate processes/threads must wait.
    with admission.output_owner(out_root, [_db_path(con), Path(src_dir),
            Path(receipt_path) if receipt_path else Path(out_root) / 'compile-receipt.json']):
        while True:
            stats = place_tree(src_dir, src_bid, out_root, con, raw_dir=raw_dir,
                receipt_path=receipt_path, no_compile_gate=no_compile_gate)
            print(json.dumps(stats, sort_keys=True), flush=True)
            _watch_wait(interval)


def freeze_parameters(params, root):
    result = dict(params)
    for name in ('db', 'out-dir', 'raw-dir'):
        if not result.get(name): raise ValueError('cross_place_requires_' + name)
        p = Path(result[name]);result[name] = str((p if p.is_absolute() else root / p).absolute())
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
    from . import source_contribution
    return {str(Path(p).resolve()): admission.digest(Path(p).read_bytes()) for p in
            (__file__, admission.__file__, source_contribution.__file__)}


def guarded_command(params):
    root = str(Path(__file__).resolve().parents[2])
    return [sys.executable, '-I', '-S', '-c', _BOOTSTRAP, root, json.dumps({'params': params, 'implementation': _implementation()}, sort_keys=True)]


def command_matches(argv, params):
    return argv == guarded_command(params)


def guarded_main(raw):
    payload = json.loads(raw)
    if payload['implementation'] != _implementation(): raise ValueError('cross_place_implementation_changed')
    params = payload['params']
    args = ['--from', params['from'], '--db', params['db'], '--out-dir', params['out-dir'],
            '--repo', params['repo'], '--raw-dir', params['raw-dir'], '--byteexact-receipt', params['byteexact-receipt']]
    if params.get('watch'): args += ['--watch', '--interval', str(params.get('interval', 8))]
    if params.get('no-compile-gate'): args += ['--no-compile-gate']
    raise SystemExit(main(args))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='program', required=True)
    ap.add_argument('--db', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--raw-dir', type=Path, required=True)
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--interval', type=float, default=8.0)
    ap.add_argument('--byteexact-receipt', type=Path)
    ap.add_argument('--no-compile-gate', action='store_true')
    args = ap.parse_args(argv)
    with admission.read_database(args.db) as con:
        brow = con.execute('SELECT id FROM binary WHERE repo_path=?', (args.repo,)).fetchone()
        if not brow: raise ValueError('source_binary_not_in_database')
        src_dir = resolve_source_dir(args.out_dir, args.program)
        if src_dir is None: raise ValueError('no_source_directory')
        kw = {'raw_dir': args.raw_dir, 'receipt_path': args.byteexact_receipt,
              'no_compile_gate': args.no_compile_gate}
        if args.watch: watch(src_dir, int(brow['id']), args.out_dir, con, args.interval, **kw)
        else: print(json.dumps(place_tree(src_dir, int(brow['id']), args.out_dir, con, **kw), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
