"""Owned synthetic continuation fixtures; no services or production corpus."""
import json
import os
from pathlib import Path
import threading
import sys

import pytest

from agentdecompile_recovery.corpus import cross_place as cp
from agentdecompile_recovery.corpus import cross_place_admission as gate
from agentdecompile_recovery.corpus import cross_place_checkpoint as checkpoint
from test_cross_place_admission import fixture

# See test_cross_place_admission.py: the shared ``fixture`` already skips
# itself when the pinned /usr/bin/clang-22 compiler isn't installed, which
# covers every test here that requests it (the module-level skip previously
# tried here would have also skipped tests that don't use ``fixture``).


def test_real_129_eligible_keys_across_guarded_generations_and_replay(fixture):
    f = fixture
    # One source fans out to 129 genuinely eligible physical recipients.
    # Membership chunking cannot avoid the production128 admission boundary.
    template = f['con'].execute('SELECT * FROM binary WHERE id=2').fetchone()
    recipient_address = f['addresses'][1]
    for bid in range(3, 131):
        slug = f'recipient-{bid}.exe'
        raw = bytearray((f['images'] / 'recipient.exe').read_bytes())
        raw[-1] = bid
        (f['images'] / slug).write_bytes(raw)
        f['con'].execute('INSERT INTO binary(id,repo_path,slug,content_sha256,arch,bits,format) VALUES(?,?,?,?,?,?,?)',
            (bid, '/' + slug, slug, gate.digest(raw), 'x86', 32, 'pe'))
        f['con'].execute('INSERT INTO func(binary_id,addr,name,size,is_thunk,return_type,param_count,param_types,calling_convention) VALUES(?,?,?,?,?,?,?,?,?)',
            (bid, recipient_address, 'leaf', 6, 0, 'int', 0, '[]', '__cdecl'))
        f['con'].execute('INSERT INTO identity(logical_id,binary_id,addr,confidence,method,evidence) VALUES(?,?,?,?,?,?)',
            (1, bid, recipient_address, 1.0, 'fixture-candidate-link', json.dumps({'dependencies': []})))
    f['con'].commit()
    params = cp.freeze_parameters({'from': 'donor', 'repo': '/donor.exe',
        'db': str(f['db']), 'out-dir': str(f['out']), 'raw-dir': str(f['images'])}, f['root'])
    invocations = []
    def execute(argv, fds, cancel):
        assert argv[1:4] == ['-I', '-S', '-c']
        assert cp.command_matches(argv, params)
        result = cp._standalone_execute(argv, fds, cancel)
        cursor = json.loads((f['out'] / gate.AREA / 'checkpoint/scan.json').read_text())
        invocations.append({'generation': json.loads(argv[-1])['generation'], 'code': result[0], 'scan': cursor})
        return result
    assert cp.supervise(params, execute=execute)[0] == 0
    area = f['out'] / gate.AREA
    manifests = list((area / 'qualified-candidates').glob('*/manifest.json'))
    assert len(manifests) == 129
    recipients = {json.loads(p.read_text())['recipient']['binaryId'] for p in manifests}
    assert recipients == set(range(2, 131))
    # All 129 observations originate in real fresh cc1 runs, not unsupported
    # proposals or mocked compiler counters. A second epoch reuses publication.
    observations = [json.loads(p.read_text())['evidence']['provider']['compileObservation'] for p in manifests]
    assert len({o['invocation'] for o in observations}) == 129
    assert all(o['returncode'] == 0 and Path(o['object']['path']).is_file() for o in observations)
    assert len(invocations) == 2
    assert [item['code'] for item in invocations] == [75, 0]
    assert invocations[0]['scan']['sealed'] is True
    assert invocations[0]['scan']['cursor'][2] == [129, recipient_address]
    assert invocations[1]['scan']['sealed'] is False
    retained = sorted(str(p) for p in (area / 'producer-evidence').glob('qualification-*'))
    assert len(retained) == 129
    assert cp.supervise(params, execute=execute)[0] == 0
    assert sorted(str(p) for p in (area / 'producer-evidence').glob('qualification-*')) == retained


def test_attempt_reservation_survives_new_ledger_and_clock_rollback(tmp_path, monkeypatch):
    ledger = checkpoint.Ledger(tmp_path / '.cross-place')
    key = 'a' * 64
    monkeypatch.setattr(checkpoint.time, 'time', lambda: 1000)
    assert ledger.reserve(key)[0]
    restored = checkpoint.Ledger(tmp_path / '.cross-place')
    assert not restored.reserve(key)[0]
    monkeypatch.setattr(checkpoint.time, 'time', lambda: 900)
    assert not restored.reserve(key)[0]
    monkeypatch.setattr(checkpoint.time, 'time', lambda: 1031)
    assert restored.reserve(key)[0]
    monkeypatch.setattr(checkpoint.time, 'time', lambda: 10000)
    assert not checkpoint.Ledger(tmp_path / '.cross-place').reserve(key)[0]
    assert restored.get(key)['count'] == 2


def test_finite_sealed_epochs_revisit_head_under_tail_append(tmp_path):
    out = tmp_path / 'output'; src = out / 'source'; src.mkdir(parents=True)
    receipt = out / 'receipt.json'; receipt.write_text('{}')
    index = checkpoint.PublicationIndex(out)
    with index.locked():
        for i in range(140):
            path = src / f'z{i:04d}.c'; path.write_text('source'); index.append(path, receipt)
    ledger = checkpoint.Ledger(out / '.cross-place')
    scan = checkpoint.Scan(ledger, src, {'receipt': str(receipt)})
    initial = scan.pending(); assert len(initial) == 128
    with index.locked():
        earlier = src / 'a-inserted.c'; earlier.write_text('source'); index.append(earlier, receipt)
    assert scan.pending() == initial
    scan.finish()
    visited = set()
    for epoch in range(4):
        scan = checkpoint.Scan(ledger, src, {'receipt': str(receipt)})
        visited.update(path.name for path, _ in scan.pending())
        with index.locked():
            path = src / f'tail-{epoch}.c'; path.write_text('source'); index.append(path, receipt)
        scan.finish()
    assert 'a-inserted.c' in visited
    assert 'z0139.c' in visited


def test_unlocked_same_inode_rejected_without_acquiring(tmp_path):
    root = tmp_path / '.cross-place'; root.mkdir()
    lock = root / '.owner.lock'; lock.touch()
    fd = os.open(lock, os.O_RDWR)
    try:
        with pytest.raises(ValueError, match='not_preheld'): gate._held_descriptor(fd, root)
        assert 'lock:' not in Path(f'/proc/self/fdinfo/{fd}').read_text()
        with gate.output_owner(tmp_path, []):
            with pytest.raises(ValueError, match='not_preheld'): gate._held_descriptor(fd, root)
    finally: os.close(fd)


def test_btrfs_lock_device_namespace_not_equated_to_fstat(tmp_path, monkeypatch):
    with gate.output_owner(tmp_path, []) as root:
        fd = gate.lease_fds()[0]
        original = Path.read_text
        inode = os.fstat(fd).st_ino
        def read(path, *args, **kw):
            if str(path) == f'/proc/self/fdinfo/{fd}':
                # Actual NVMe probe exhibited fstat device45 vs lock00:23.
                return f'pos:\t0\nino:\t{inode}\nlock:\t1: FLOCK ADVISORY WRITE 2105212 00:23:{inode} 0 EOF\n'
            return original(path, *args, **kw)
        monkeypatch.setattr(Path, 'read_text', read)
        assert gate._held_descriptor(fd, root).st_ino == inode


@pytest.mark.parametrize('handoff_failure', [None, 'worker', 'compiler'])
def test_actual_compiler_retains_lease_after_supervisor_and_worker_exit(fixture, handoff_failure):
    """Real fixed cc1 spawn; SIGSTOP supplies an explicitly acknowledged observation window."""
    import ctypes
    import signal
    import subprocess
    import time
    from agentdecompile_recovery.corpus.supervision import process_identity
    f = fixture
    root = Path(cp.__file__).resolve().parents[2]
    marker = f['root'] / 'compiler-held.json'
    config = f['root'] / 'lease-config.json'
    config.write_text(json.dumps({**{k: str(f[k]) for k in ('out', 'src', 'db', 'images', 'receipt')}, 'handoff_failure': handoff_failure}))
    helper = f['root'] / 'lease-child.py'
    helper.write_text(r'''
import os,sys,json,time,signal,subprocess
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1])
from agentdecompile_recovery.corpus import cross_place as cp,cross_place_admission as gate,source_contribution as sc
from agentdecompile_recovery.corpus.supervision import process_identity
mode,config,marker=sys.argv[2:5];c=json.loads(Path(config).read_text())
def write(path,value):
 if c.get('handoff_failure') and str(path)==marker+'.'+c['handoff_failure']:
  print(json.dumps({'injectedHandoffFailure':c['handoff_failure']}),flush=True)
  raise SystemExit(73)
 p=Path(str(path)+'.pending');p.write_text(json.dumps(value));os.replace(p,path)
if mode=='supervisor':
 with gate.output_owner(c['out'],[]) as area:
  envelope=gate.lease_envelope(c['out'])
  child=subprocess.Popen([sys.executable,'-I','-S',__file__,sys.argv[1],'worker',config,marker,json.dumps(envelope)],pass_fds=gate.lease_fds(),start_new_session=True)
  try:
   print(json.dumps({'ownedSpawn':process_identity(child.pid),'role':'worker'}),flush=True)
   write(marker+'.worker',process_identity(child.pid))
   raise SystemExit(child.wait(timeout=120))
  finally:
   try:os.killpg(child.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   child.wait(timeout=3)
else:
 envelope=json.loads(sys.argv[5]);original=sc.subprocess.run
 def capture(argv,**kw):
  if '-cc1' not in argv:return original(argv,**kw)
  assert tuple(kw['pass_fds'])==gate.lease_fds()
  for attempt in range(3):
   child=subprocess.Popen(argv,cwd=kw['cwd'],env=kw['env'],pass_fds=kw['pass_fds'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    identity=process_identity(child.pid)
    print(json.dumps({'ownedSpawn':identity,'role':'compiler'}),flush=True)
    write(marker+'.compiler',identity)
    write(marker+'.compiler-attempt-'+str(attempt),identity)
    if child.poll() is not None:
     child.communicate(timeout=3);continue
    os.kill(child.pid,signal.SIGSTOP)
    deadline=time.monotonic()+3
    while child.poll() is None:
     state=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()[0]
     if state in ('T','t'):break
     if time.monotonic()>deadline:raise TimeoutError('compiler stop acknowledgement')
     time.sleep(.01)
    if child.poll() is not None:
     child.communicate(timeout=3);continue
    fd=kw['pass_fds'][0]
    proof={'supervisor':envelope['supervisor'],'worker':process_identity(os.getpid()),'compiler':identity,
           'argv':argv,'exe':str(Path(f'/proc/{child.pid}/exe').resolve()),'descriptor':fd,'spawnAttempt':attempt,
           'fdinfo':Path(f'/proc/{child.pid}/fdinfo/{fd}').read_text(),'object':argv[argv.index('-o')+1]}
    write(marker,proof)
    stdout,stderr=child.communicate(timeout=100)
    return subprocess.CompletedProcess(argv,child.returncode,stdout,stderr)
   except BaseException:
    if child.poll() is None:child.kill()
    child.wait(timeout=3)
    raise
  raise RuntimeError('compiler_exited_before_stop_ack_after_three_owned_attempts')

 sc.subprocess.run=capture
 with gate.borrowed_owner(envelope):
  with gate.read_database(c['db']) as con:
   cp.place_tree(c['src'],1,c['out'],con,raw_dir=c['images'],receipt_path=c['receipt'])
''')
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    try:
        log = (f['root'] / 'lease-child.log').open('w')
        owner = subprocess.Popen([sys.executable, '-I', '-S', str(helper), str(root),
            'supervisor', str(config), str(marker)], stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    except BaseException:
        if 'log' in locals(): log.close()
        libc.prctl(36, previous.value, 0, 0, 0)
        raise
    owner_id = process_identity(owner.pid)
    owned = [owner_id]; proof = None
    def same(identity):
        return process_identity(identity['pid']) == identity
    def wait_orphan(identity):
        if not same(identity): return None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                pid, status = os.waitpid(identity['pid'], os.WNOHANG)
                if pid: return os.waitstatus_to_exitcode(status)
            except ChildProcessError:
                if not Path(f'/proc/{identity["pid"]}').exists(): return None
            time.sleep(.01)
        raise TimeoutError('owned orphan did not reap')
    try:
        if handoff_failure:
            assert owner.wait(timeout=60) == 73
            for line in (f['root'] / 'lease-child.log').read_text().splitlines():
                try: item = json.loads(line)
                except ValueError: continue
                if isinstance(item, dict) and item.get('ownedSpawn'):
                    owned.append(item['ownedSpawn'])
            assert len(owned) >= 2
            for identity in reversed(owned[1:]): wait_orphan(identity)
            assert all(not same(identity) for identity in owned)
            with gate.output_owner(f['out'], []): pass
            return
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert owner.poll() is None, (f['root'] / 'lease-child.log').read_text()
            if time.monotonic() > deadline: raise TimeoutError('actual compiler readiness')
            time.sleep(.02)
        proof = json.loads(marker.read_text())
        owned += [proof['worker'], proof['compiler']]
        assert all(same(identity) for identity in owned)
        assert 'FLOCK' in proof['fdinfo'] and 'WRITE' in proof['fdinfo']
        assert '-cc1' in proof['argv'] and Path(proof['argv'][0]).samefile('/usr/bin/clang-22')
        assert Path(proof['exe']).samefile('/usr/bin/clang-22')
        assert same(owner_id)
        os.kill(owner.pid, signal.SIGKILL)
        assert owner.wait(timeout=3) == -signal.SIGKILL
        assert same(proof['worker'])
        os.kill(proof['worker']['pid'], signal.SIGKILL)
        assert wait_orphan(proof['worker']) == -signal.SIGKILL
        assert same(proof['compiler'])
        # Both Python owners are gone; the actual native writer holds the FD.
        with pytest.raises(ValueError, match='candidate_output_owned'):
            with gate.output_owner(f['out'], []): pass
        assert same(proof['compiler'])
        os.kill(proof['compiler']['pid'], signal.SIGCONT)
        assert wait_orphan(proof['compiler']) == 0
        assert Path(proof['object']).is_file()
        with gate.output_owner(f['out'], []): pass
    finally:
        cleanup_errors = []
        try:
            try:
                lines = (f['root'] / 'lease-child.log').read_text().splitlines()
                for line in lines:
                    try: item = json.loads(line)
                    except ValueError: continue
                    if isinstance(item, dict) and item.get('ownedSpawn') and item['ownedSpawn'] not in owned:
                        owned.append(item['ownedSpawn'])
            except (OSError, ValueError) as exc: cleanup_errors.append(str(exc))
            for suffix in ('.worker', '.compiler'):
                try:
                    path = Path(str(marker) + suffix)
                    if path.exists():
                        identity = json.loads(path.read_text())
                        if identity not in owned: owned.append(identity)
                except (OSError, ValueError) as exc: cleanup_errors.append(str(exc))
            for identity in reversed(owned):
                try:
                    if same(identity): os.kill(identity['pid'], signal.SIGKILL)
                except ProcessLookupError: pass
                except OSError as exc: cleanup_errors.append(str(exc))
            try: owner.wait(timeout=3)
            except subprocess.TimeoutExpired as exc: cleanup_errors.append(str(exc))
            for identity in reversed(owned[1:]):
                try: wait_orphan(identity)
                except (OSError, TimeoutError) as exc: cleanup_errors.append(str(exc))
        finally:
            log.close()
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0
        assert not cleanup_errors, cleanup_errors


def test_real_native_negative_budget_survives_new_guarded_epochs(fixture):
    from test_cross_place_admission import pe, bulk
    from agentdecompile_recovery.corpus import source_contribution as sc
    f = fixture
    for bid, slug, offset in [(1, 'donor.exe', 0), (2, 'recipient.exe', 16)]:
        raw, _ = pe(value=0, offset=offset)
        (f['images'] / slug).write_bytes(raw)
        f['con'].execute('UPDATE binary SET content_sha256=? WHERE id=?', (gate.digest(raw), bid))
    f['con'].commit()
    f['source'].write_text(f['source'].read_text().replace('return 7', 'return 0'))
    ok, error = bulk._compile_text(f['source'], f['root'] / 'zero-producer.obj', 'leaf', '', f['source'].read_text())
    assert ok, error
    f['receipt'].write_text(json.dumps({'results': [{'ok': True, **bulk._COMPILE_BINDINGS[str(f['source'])]}]}))
    params = cp.freeze_parameters({'from': 'donor', 'repo': '/donor.exe', 'db': str(f['db']),
        'out-dir': str(f['out']), 'raw-dir': str(f['images'])}, f['root'])
    assert cp.supervise(params)[0] == 0
    area = f['out'] / gate.AREA
    workspaces = sorted((area / 'producer-evidence').glob('qualification-*'))
    assert len(workspaces) == 1
    entries = [checkpoint.read(p) for p in (area / 'checkpoint/entries').glob('*/*.json')]
    assert len(entries) == 1 and entries[0]['count'] == 1 and entries[0]['state'] == 'deterministic'
    f['con'].execute("INSERT INTO logical_function(id,best_name) VALUES(999,'unrelated')")
    f['con'].commit()
    assert cp.supervise(params)[0] == 0
    assert sorted((area / 'producer-evidence').glob('qualification-*')) == workspaces
    assert [checkpoint.read(p) for p in (area / 'checkpoint/entries').glob('*/*.json')] == entries
    objects = list(workspaces[0].glob('contribution-*/unit.obj'))
    assert len(objects) == 1
    assert sc.parse_coff(objects[0].read_bytes())['bytes'] in (b'\x31\xc0\xc3', b'\x33\xc0\xc3')
    assert not list((area / 'qualified-candidates').glob('*/manifest.json'))
