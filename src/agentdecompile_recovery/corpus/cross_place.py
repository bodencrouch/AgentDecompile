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


def load_byteexact_ok_ids(path: Path) -> set[str] | None:
    """Fresh verifier receipts admit only individually relocation-masked exact C."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list) or data.get("total") != len(rows):
        return None
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("ok"):
            continue
        addr = str(row.get("addr") or "").strip().lower().removeprefix("0x")
        try:
            out.add(f"{int(addr, 16):x}")
        except ValueError:
            continue
    return out or None


def _addr_token(addr: int) -> str:
    return f"{addr:x}"


def place_tree(
    src_dir: Path,
    src_bid: int,
    out_root: Path,
    con,
    *,
    compile_ok: set[str] | None = None,
) -> dict:
    if compile_ok is not None and not compile_ok:
        return {
            "placed": 0,
            "skipped_no_addr": 0,
            "src_linked": 0,
            "reason": "no compile receipt",
        }
    index = load_index(con, src_bid)
    placed = skipped = 0
    for cfile in sorted(src_dir.glob("*.c")):
        if cfile.name.startswith("_"):
            continue
        head = cfile.read_text(errors="replace")[:800]
        addr = parse_addr(head)
        if addr is None:
            skipped += 1
            continue
        if compile_ok is not None and _addr_token(addr) not in compile_ok:
            skipped += 1
            continue
        placed += place_one(cfile, addr, index, out_root)
    return {"placed": placed, "skipped_no_addr": skipped, "src_linked": len(index)}


def place_one(src_path, src_addr, index, out_root, *, con=None, src_bid=None,
              raw_dir=None, receipt_path=None, no_compile_gate=False):
    """Legacy address-only callers refuse; all real routes pass current context."""
    if con is None or src_bid is None:
        return 0
    result = place_tree(Path(src_path).parent, src_bid, out_root, con, raw_dir=raw_dir,
        receipt_path=receipt_path, no_compile_gate=no_compile_gate, source_paths=[Path(src_path)])
    return result['placed']

    compile_ok = load_compile_ok_ids(out_root)
    if compile_ok is None or not compile_ok:
        print("cross-place watch: no compile receipt; copy 0", flush=True)
        return
    index = load_index(con, src_bid)
    seen: dict[str, float] = {}
    print(f"cross-place watch {src_dir} -> {len(index)} linked addrs", flush=True)
    while True:
        n = 0
        for cfile in sorted(src_dir.glob("*.c")):
            if cfile.name.startswith("_"):
                continue
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

    from .store import connect

    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="program", required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=float, default=8.0)
    ap.add_argument("--byteexact-receipt", type=Path,
                    help="completed verify-byteexact receipt; place only its individually exact C")
    ap.add_argument("--no-compile-gate", action="store_true",
                    help="place any real-C with an address (skip the source compile-receipt gate); "
                         "for cross-binary seeding where the shared receipt does not match the source")
    args = ap.parse_args(argv)
    con = connect(args.db)
    brow = con.execute("SELECT id FROM binary WHERE repo_path=?", (args.repo,)).fetchone()
    if not brow:
        raise SystemExit(f"not in database: {args.repo}")
    dump_tree = args.out_dir / "dump-source"
    src_dir = resolve_source_dir(args.out_dir, args.program)
    if src_dir is None:
        raise SystemExit(
            f"no recovered C under {args.out_dir / args.program} or {dump_tree}. "
            "Recover → Dump source writes C under dump-source, then run Cross-place."
        )
    compile_ok = (load_byteexact_ok_ids(args.byteexact_receipt) if args.byteexact_receipt
                  else None if args.no_compile_gate else load_compile_ok_ids(args.out_dir))
    if not args.no_compile_gate and (compile_ok is None or not compile_ok):
        print(f"cross-place {args.program}: {{'placed': 0, 'reason': 'no usable exact receipt'}}")
        return 0
    if args.watch:
        watch(src_dir, int(brow["id"]), args.out_dir, con, args.interval)
        return 0
    stats = place_tree(src_dir, int(brow["id"]), args.out_dir, con, compile_ok=compile_ok)
    print(f"cross-place {args.program}: {stats}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
