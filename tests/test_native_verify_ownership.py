"""Catalog-only native ownership, with tiny sequential real Clang fixtures.

All package/compiler outputs belong to pytest's NVMe/tmpfs basetemp. No services,
game, Ghidra, corpus writes or whole-image recovery are used.
"""
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import Mock

import pytest

from agentdecompile_recovery import native_verify_contract as contract
from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
from agentdecompile_recovery.corpus.dashboard.actions.catalog import action_by_id, apply_defaults, build_command

# native_verify_contract pins the qualified compiler to the exact,
# administrator-installed /usr/bin/clang-22 (see its module docstring: "no
# Wine, wrappers, custom flags" -- the whole point is a fixed, owned
# toolchain). Tests that actually dispatch a real compile through that
# contract cannot run offline in an environment where that package isn't
# installed at that path; skip just those, not the ones that only exercise
# rejection paths before any real compiler is touched.
_NEEDS_REAL_COMPILER = not contract.COMPILER.exists()
_SKIP_REASON = f"requires the pinned {contract.COMPILER} compiler; not installed in this environment"


@pytest.fixture
def scope(tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog
    monkeypatch.setattr(catalog, "env_defaults", lambda: {})
    monkeypatch.setattr(job_history, "directory", lambda: tmp_path / "receipts")
    monkeypatch.setattr(job_history, "owner", lambda: {"ownerPid": os.getpid(), "ownerStart": "synthetic"})
    monkeypatch.setattr(jobs, "live_root", lambda: tmp_path)
    action = action_by_id(contract.ACTION)
    assert action and action.mutating and action.long_running
    stores = []
    def store():
        result = jobs.JobStore()
        stores.append(result)
        return result
    yield tmp_path, action, store
    for item in stores:
        if item._resource_owner_handle and not item._resource_owner_handle.closed:
            item._resource_owner_handle.close()


def package(root, language="c", text="int answer(void) { return 42; }\n"):
    root.mkdir(parents=True)
    (root / "candidate.c").write_text(text)
    (root / "metadata.json").write_text(json.dumps({"sourceLanguage": language}))
    (root / "manifest.json").write_text(json.dumps({"functions": [
        {"source": str(root / "candidate.c"), "metadata": str(root / "metadata.json")}
    ]}))
    return root


def insert(store, action, root, params, identity="123456789abc"):
    params = apply_defaults(action, params)
    job = jobs.JobRecord(id=identity, action_id=action.id, title=action.title,
                         params=params, argv=build_command(action, params), execution_root=str(root))
    store._jobs[job.id] = job
    store._order.append(job.id)
    return job


@pytest.mark.parametrize("language,target", [("c", "i686-pc-windows-msvc"), ("c++", "x86_64-pc-windows-msvc")])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_real_catalog_compile_has_bound_durable_release(scope, language, target):
    root, action, factory = scope
    pkg = package(root / "package", language)
    store = factory()
    job = insert(store, action, root, {"package": str(pkg), "clang-target": target})
    store._run(job.id, threading.Event())
    assert job.status == "ok", job.log or job.error
    output = pkg / "verification"
    assert job.resource_keys == {"external": [["output", str(output)]]}
    assert job.resource_disposition == "released" and jobs._bound_clearance(job.to_dict())
    assert contract.command_matches(job.argv, job.params)
    report = json.loads((output / "verification.json").read_text())
    assert report["objectCompileOk"] == 1
    assert (output / "candidate.o").stat().st_size > 0
    assert (output / ("candidate.verify.cpp" if language == "c++" else "candidate.verify.c")).exists()
    for name in ("syntax", "object"):
        assert (output / f"candidate.{name}.stdout.txt").exists()
        assert (output / f"candidate.{name}.stderr.txt").exists()
    durable = json.loads((root / "receipts" / f"{job.id}.json").read_text())
    assert jobs._bound_clearance(durable)
    assert store.reconciliation_report(job.id)["eligible"]
    assert not store._external_held
    witness = json.loads(job.log)["nativeExecution"]
    assert witness["profile"] == contract.PROFILE
    assert witness["modules"]["agentdecompile_recovery.native_verify_contract"]["path"] == str(Path(contract.__file__).resolve())


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_cwd_relative_inputs_and_literal_tilde_output(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    (root / "candidate.c").write_text("int cwd_source(void) { return 7; }\n")
    (pkg / "manifest.json").write_text(json.dumps({"functions": [{"source": "candidate.c", "metadata": str(pkg / "metadata.json") }]}))
    monkeypatch.chdir(root)
    store = factory()
    job = insert(store, action, root, {"package": "package", "out-dir": "~/owned"})
    store._run(job.id, threading.Event())
    assert job.status == "ok", job.log
    output = root / "~" / "owned"
    assert job.params["out-dir"] == str(output)
    assert "cwd_source" in (output / "candidate.verify.c").read_text()
    assert job.resource_keys["external"] == [["output", str(output)]]


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_context_output_freezes_and_injected_success_quarantines(scope):
    root, action, factory = scope
    pkg = package(root / "package")
    params = apply_defaults(action, {"package": str(pkg)}, {"work_dir": str(root / "context")})
    store = factory()
    job = insert(store, action, root, params)
    store.executor = lambda *a: (0, "{}")
    store._run(job.id, threading.Event())
    assert job.resource_keys == {"external": [["output", str(root / "context")]]}
    assert job.resource_disposition == "quarantined"
    assert not jobs._bound_clearance(job.to_dict())
    assert not store.reconciliation_report(job.id)["eligible"]


@pytest.mark.parametrize("kind,relation", [("output", "equal"), ("project", "ancestor"), ("store", "descendant")])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_overlaps_block_and_nonoverlap_remains_eligible(scope, monkeypatch, kind, relation):
    root, action, factory = scope
    pkg = package(root / "package")
    output = root / "owned"
    held = output if relation == "equal" else root if relation == "ancestor" else output / "inner"
    store = factory()
    store._restore_reservations_locked()
    store._external_held[(kind, str(held))] = "other"
    job = insert(store, action, root, {"package": str(pkg), "out-dir": str(output)})
    store.executor = Mock(return_value=(0, "{}"))
    cancel = threading.Event()
    monkeypatch.setattr(jobs.time, "sleep", lambda _: cancel.set())
    store._run(job.id, cancel)
    store.executor.assert_not_called()
    assert store._running == 0
    # A sibling outside the held ancestor remains eligible, injected executor
    # deliberately leaves that new claim quarantined rather than minting proof.
    other = root.parent / (root.name + "-independent")
    healthy = insert(store, action, root, {"package": str(pkg), "out-dir": str(other)}, "abcdef123456")
    store._run(healthy.id, threading.Event())
    assert store.executor.call_count == 1


@pytest.mark.parametrize("flags", [["-Xclang", "-load", "/outside/plugin.so"], ["@/outside/response"], ["--config=/outside/config"], ["-MF", "/outside/deps"], ["-B/outside"], ["-resource-dir", "/outside"]])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_actual_child_rejects_metadata_changed_after_command_construction(scope, flags):
    root, action, factory = scope
    pkg = package(root / "package")
    params = contract.freeze_parameters({"package": str(pkg)}, root)
    argv = contract.guarded_command(params)
    (pkg / "metadata.json").write_text(json.dumps({"compilerProfileHints": {"args": flags}}))
    code, log = jobs._default_executor(argv, root, threading.Event())
    assert code != 0 and "unsupported effective native compiler" in log
    assert not (pkg / "verification").exists()


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_real_child_drops_environment_and_implicit_driver_config(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    hostile = root / "hostile"
    hostile.mkdir()
    marker = root / "python-injection"
    (hostile / "sitecustomize.py").write_text(f"open({str(marker)!r},'w').write('bad')")
    (hostile / "clang.cfg").write_text("-Xclang -load -Xclang /nonexistent-plugin.so\n")
    for key, value in {"PYTHONPATH": str(hostile), "PYTHONHOME": str(hostile),
                       "LD_PRELOAD": "/nonexistent-preload.so", "CCC_OVERRIDE_OPTIONS": "+-invalid-flag",
                       "CLANG_CONFIG_FILE_USER_DIR": str(hostile), "COMPILER_PATH": str(hostile),
                       "LLVM_PROFILE_FILE": str(hostile / "profile"), "TMPDIR": str(hostile),
                       "HOME": str(hostile)}.items():
        monkeypatch.setenv(key, value)
    store = factory()
    job = insert(store, action, root, {"package": str(pkg)})
    store._run(job.id, threading.Event())
    assert job.status == "ok", job.log
    assert not marker.exists() and not (hostile / "profile").exists()
    assert "cannot be preloaded" not in job.log
    report = json.loads((pkg / "verification" / "verification.json").read_text())
    assert "--no-default-config" in report["results"][0]["syntax"]["command"]
    assert list((pkg / "verification").glob(".native-verify-*"))


@pytest.mark.parametrize("options", [{"compiler": "msvc"}, {"clang": "/bin/false"}, {"clang-arg": ["-O2"]}, {"code-compare": True}, {"clang-target": "arm-linux-gnu"}])
def test_unsupported_profile_never_dispatches(scope, options):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg), **options})
    store.executor = Mock()
    store._run(job.id, threading.Event())
    store.executor.assert_not_called()
    assert job.status == "failed"
    assert not (pkg / "verification").exists()


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_output_leaf_cannot_redirect_write(scope, link):
    root, action, factory = scope
    pkg = package(root / "package")
    output = pkg / "verification"
    output.mkdir()
    protected = root / "protected"
    protected.write_text("unchanged")
    leaf = output / "candidate.verify.c"
    if link == "symlink":
        leaf.symlink_to(protected)
    else:
        os.link(protected, leaf)
    argv = contract.guarded_command(contract.freeze_parameters({"package": str(pkg)}, root))
    code, log = jobs._default_executor(argv, root, threading.Event())
    assert code != 0 and "native verifier output" in log
    assert protected.read_text() == "unchanged"


@pytest.mark.parametrize("status,keys", [("ok", None), ("interrupted", {}), ("failed", {})])
def test_old_unguarded_receipt_derives_and_retains_default_output(scope, status, keys):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg)})
    row = job.to_dict()
    row.update(status=status, resourceKeys=keys, resourceDisposition="unreserved", returncode=0)
    folder = root / "receipts"
    folder.mkdir()
    (folder / f"{job.id}.json").write_text(json.dumps(row))
    store._jobs.clear()
    store._restore_reservations_locked()
    assert store._external_held[("output", str(pkg / "verification"))] == job.id
    assert not store.reconciliation_report(job.id)["eligible"]


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_historical_unguarded_argv_cannot_inherit_native_release(scope):
    root, action, factory = scope
    pkg = package(root / "package")
    params = contract.freeze_parameters({"package": str(pkg)}, root)
    row = {"actionId": contract.ACTION, "params": params,
           "argv": build_command(action, params), "id": "123456789abc",
           "executionAttempt": "attempt", "resourceKeys": {"external": [["output", params["out-dir"]]]},
           "executionOwner": {"pid": 1, "start_ticks": "1", "boot_id": "boot"}}
    import hashlib
    row["clearanceObservation"] = {"source": "local-executor-session-observer-v1", "jobId": row["id"],
        "attempt": row["executionAttempt"], "resourceKeys": row["resourceKeys"], "process": row["executionOwner"],
        "argvDigest": hashlib.sha256(json.dumps(row["argv"], separators=(",", ":")).encode()).hexdigest(),
        "sessionClearance": "clear"}
    assert not jobs._bound_clearance(row)


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_receipt_persistence_failure_quarantines_real_compiler(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg)})
    from agentdecompile_recovery.corpus import supervision
    original = supervision.save_state
    def save(path, payload):
        if payload.get("resourceDisposition") == "released":
            raise OSError("synthetic receipt failure")
        return original(path, payload)
    monkeypatch.setattr(supervision, "save_state", save)
    store._run(job.id, threading.Event())
    assert (pkg / "verification" / "candidate.o").exists()
    assert job.resource_disposition == "quarantined" and store._running == 0
    assert store._external_held


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_policy_revalidates_actual_effective_args_before_first_write(tmp_path, monkeypatch):
    from agentdecompile_recovery import package_verify
    pkg = package(tmp_path / "package")
    output = pkg / "verification"
    policy = contract.NativePolicy(output)
    original = policy.prepare
    def prepare(path, manifest):
        original(path, manifest)
        (pkg / "metadata.json").write_text(json.dumps({"compilerProfileHints": {"args": ["-save-temps"]}}))
    monkeypatch.setattr(policy, "prepare", prepare)
    with pytest.raises(ValueError, match="effective native compiler"):
        package_verify.verify_recovered_source_package(pkg, out_dir=output, _native_policy=policy)
    assert not (output / "candidate.verify.c").exists()
    assert not (output / "candidate.o").exists()


@pytest.mark.parametrize("name", ["candidate.o", "verification.json"])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_target_slice_selected_input_is_preserved_even_without_code_compare(scope, name):
    root, action, factory = scope
    pkg = package(root / "package")
    output = pkg / "verification"
    output.mkdir()
    sentinel = output / name
    sentinel.write_text("selected target bytes")
    (pkg / "metadata.json").write_text(json.dumps({"targetSlice": {"packagedBytesPath": str(sentinel)}}))
    argv = contract.guarded_command(contract.freeze_parameters({"package": str(pkg)}, root))
    code, log = jobs._default_executor(argv, root, threading.Event())
    assert code != 0 and "contains selected package input" in log
    assert sentinel.read_text() == "selected target bytes"


def test_unapproved_resource_tree_is_not_enrolled_by_json(tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus import source_contribution
    resource = tmp_path / "resource"
    resource.mkdir()
    (resource / "injected.h").write_text("/* unapproved */")
    monkeypatch.setattr(contract, "RESOURCE", resource)
    monkeypatch.setattr(source_contribution, "_toolchain", lambda _: [])
    with pytest.raises(ValueError, match="unapproved clang driver resource tree"):
        contract._check_toolchain()


def test_missing_tool_identity_refuses_before_output(tmp_path, monkeypatch):
    from agentdecompile_recovery import package_verify
    from agentdecompile_recovery.corpus import source_contribution
    pkg = package(tmp_path / "package")
    output = pkg / "verification"
    monkeypatch.setattr(source_contribution, "_toolchain", Mock(side_effect=ValueError("unapproved_compiler_identity")))
    with pytest.raises(ValueError, match="unapproved_compiler_identity"):
        package_verify.verify_recovered_source_package(pkg, out_dir=output, _native_policy=contract.NativePolicy(output))
    assert not output.exists()


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_changed_implementation_payload_rejected_in_real_child(scope):
    root, action, factory = scope
    pkg = package(root / "package")
    argv = contract.guarded_command(contract.freeze_parameters({"package": str(pkg)}, root))
    payload = json.loads(argv[-1])
    payload["implementation"]["package_verify.py"] = "0" * 64
    argv[-1] = json.dumps(payload)
    code, log = jobs._default_executor(argv, root, threading.Event())
    assert code != 0 and "implementation changed" in log
    assert not (pkg / "verification").exists()


@pytest.mark.parametrize("mode", ["cancel", "timeout"])
@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_same_session_surviving_child_keeps_native_claim(scope, monkeypatch, mode):
    """Lifetime fault fixture uses real executor sessions, not another compiler."""
    import signal
    from agentdecompile_recovery.corpus.supervision import process_identity
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg)})
    original = jobs._default_executor
    cancel = threading.Event()
    child_pids = []
    identity_path = root / "survivor-identity.json"
    stderr_path = root / "survivor-stderr.txt"
    child = ("import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
             "print('handler-ready',flush=True);time.sleep(20)")
    # The installed test harness may have expensive sitecustomize hooks. The
    # survivor's actual signal handler, not an arbitrary startup sleep, defines
    # readiness. Its isolated startup and bounded handshake are fixture details.
    script = f"""import json,select,subprocess,sys,time
from pathlib import Path
stderr_path=Path({str(stderr_path)!r})
with stderr_path.open('w') as errors:
    p=subprocess.Popen([sys.executable,'-I','-S','-c',{child!r}],stdout=subprocess.PIPE,stderr=errors,text=True)
    start=Path('/proc/'+str(p.pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    Path({str(identity_path)!r}).write_text(json.dumps({{'pid':p.pid,'start_ticks':start}}))
    if not select.select([p.stdout],[],[],2)[0] or p.stdout.readline()!='handler-ready\\n':
        p.kill();p.wait(timeout=2)
        raise RuntimeError('survivor did not install its handler: '+stderr_path.read_text())
    print(p.pid,flush=True)
    time.sleep(20)
"""
    def fault_executor(argv, cwd, event, **kwargs):
        output_callback = kwargs.pop("on_output")
        def output(log):
            output_callback(log)
            first = log.splitlines()[0]
            if first.isdigit() and not child_pids:
                child_pids.append(int(first))
                if mode == "cancel":
                    cancel.set()
        return original([sys.executable, "-I", "-S", "-c", script], cwd, event,
                        on_output=output, timeout_seconds=3, **kwargs)
    monkeypatch.setattr(jobs, "_default_executor", fault_executor)
    try:
        store._run(job.id, cancel)
        assert child_pids
        assert "ownership remains unresolved" in job.log
        assert job.resource_disposition == "quarantined" and store._running == 0
        assert not job.clearance_observation and store._external_held
    finally:
        # Identity is recorded immediately after spawn, so a failed readiness
        # handshake is cleaned up too; never signal a reused, unrelated PID.
        if identity_path.exists():
            identity = json.loads(identity_path.read_text())
            pid = identity["pid"]
            try:
                if process_identity(pid).get("start_ticks") == identity["start_ticks"]:
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_historical_missing_execution_root_blocks_instead_of_guessing(scope):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg)})
    row = job.to_dict()
    row.update(status="ok", resourceKeys={}, executionRoot="")
    folder = root / "receipts"
    folder.mkdir()
    (folder / f"{job.id}.json").write_text(json.dumps(row))
    with pytest.raises(OSError, match="no original execution root"):
        store._restore_reservations_locked()


@pytest.mark.parametrize("explicit", [False, True])
def test_historical_missing_package_shape_never_invents_default_output(scope, explicit):
    root, action, factory = scope
    store = factory()
    params = {"package": str(root / "disappeared-package")}
    if explicit:
        params["out-dir"] = str(root / "recorded-output")
    job = insert(store, action, root, params)
    row = job.to_dict()
    row.update(status="ok", resourceKeys={})
    folder = root / "receipts"
    folder.mkdir()
    (folder / f"{job.id}.json").write_text(json.dumps(row))
    if explicit:
        store._restore_reservations_locked()
        assert store._external_held == {("output", str(root / "recorded-output")): job.id}
    else:
        with pytest.raises(OSError, match="default output is ambiguous"):
            store._restore_reservations_locked()
        assert not store._external_held


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_frozen_guarded_command_reconstruction_does_not_probe_installed_tool(tmp_path, monkeypatch):
    pkg = package(tmp_path / "package")
    params = contract.freeze_parameters({"package": str(pkg)}, tmp_path)
    argv = contract.guarded_command(params)
    assert params["clang"] == str(contract.COMPILER)
    monkeypatch.setattr(contract.shutil, "which", Mock(side_effect=AssertionError("restore must not discover tools")))
    assert contract.command_matches(argv, params)


@pytest.mark.parametrize("mode", ["unsupported", "missing-package", "cancelled"])
def test_known_predispatch_exit_does_not_poison_restoration(scope, mode):
    root, action, factory = scope
    pkg = package(root / "package") if mode != "missing-package" else root / "absent-package"
    params = {"package": str(pkg)}
    if mode != "cancelled":
        params["compiler"] = "msvc"
    store = factory()
    job = insert(store, action, root, params)
    store.executor = Mock()
    cancel = threading.Event()
    if mode == "cancelled":
        cancel.set()
    store._run(job.id, cancel)
    store.executor.assert_not_called()
    assert jobs._native_not_dispatched(job.to_dict())
    if store._resource_owner_handle:
        store._resource_owner_handle.close()
    restored = factory()
    restored._restore_reservations_locked()
    assert not restored._external_held


@pytest.mark.parametrize("tamper", ["absent", "argv", "attempt", "status", "params"])
def test_missing_or_changed_predispatch_observation_cannot_clear_legacy(scope, tamper):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    job = insert(store, action, root, {"package": str(pkg), "compiler": "msvc"})
    store._run(job.id, threading.Event())
    path = root / "receipts" / f"{job.id}.json"
    row = json.loads(path.read_text())
    assert jobs._native_not_dispatched(row)
    if tamper == "absent":
        row.pop("noDispatchObservation")
    elif tamper == "argv":
        row["argv"].append("--modified")
    elif tamper == "attempt":
        row["executionAttempt"] = "different"
    elif tamper == "status":
        row["status"] = "ok"
    else:
        row["params"]["compiler"] = "clang"
    path.write_text(json.dumps(row))
    assert not jobs._native_not_dispatched(row)
    restored = factory()
    restored._restore_reservations_locked()
    assert restored._external_held == {("output", str(pkg / "verification")): job.id}


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_actual_start_queued_receipts_do_not_reserve_and_marker_clears_before_dispatch(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    monkeypatch.setattr(threading.Thread, "start", lambda _: None)
    params = apply_defaults(action, {"package": str(pkg)})
    first = store.start(action, params, build_command(action, params))
    second = store.start(action, params, build_command(action, params))
    for job in (first, second):
        row = json.loads((root / "receipts" / f"{job.id}.json").read_text())
        assert jobs._native_not_dispatched(row)
    store.cancel(second.id)
    cancelled_pending = json.loads((root / "receipts" / f"{second.id}.json").read_text())
    assert cancelled_pending["status"] == "cancelling" and jobs._native_not_dispatched(cancelled_pending)
    store._restore_reservations_locked()
    assert not store._external_held
    def executor(*args):
        row = json.loads((root / "receipts" / f"{first.id}.json").read_text())
        assert row["resourceDisposition"] == "held"
        assert not row["noDispatchObservation"] and not jobs._native_not_dispatched(row)
        return 0, "{}"
    store.executor = executor
    store._run(first.id, threading.Event())
    assert store._jobs[first.id].resource_disposition == "quarantined"


def test_predispatch_marker_invalidation_failure_prevents_executor(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    store = factory()
    monkeypatch.setattr(threading.Thread, "start", lambda _: None)
    params = apply_defaults(action, {"package": str(pkg)})
    job = store.start(action, params, build_command(action, params))
    from agentdecompile_recovery.corpus import supervision
    original = supervision.save_state
    def save(path, payload):
        if payload.get("resourceDisposition") == "held":
            assert not payload["noDispatchObservation"]
            raise OSError("synthetic failed dispatch intent")
        return original(path, payload)
    monkeypatch.setattr(supervision, "save_state", save)
    store.executor = Mock()
    store._run(job.id, threading.Event())
    store.executor.assert_not_called()
    assert store._running == 0


@pytest.mark.skipif(_NEEDS_REAL_COMPILER, reason=_SKIP_REASON)
def test_actual_start_frozen_resource_waiter_cancellation_restores_without_claim(scope, monkeypatch):
    root, action, factory = scope
    pkg = package(root / "package")
    output = pkg / "verification"
    store = factory()
    monkeypatch.setattr(threading.Thread, "start", lambda _: None)
    params = apply_defaults(action, {"package": str(pkg)})
    job = store.start(action, params, build_command(action, params))
    store._restore_reservations_locked()
    store._external_held[("output", str(output))] = "existing-owner"
    transitional = []
    path = root / "receipts" / f"{job.id}.json"
    def cancel_while_waiting(_):
        current = store._jobs[job.id]
        assert current.params["package"] == str(pkg / "manifest.json")
        assert contract.command_matches(current.argv, current.params)
        store.cancel(job.id)
        row = json.loads(path.read_text())
        assert row["status"] == "cancelling"
        assert jobs._native_not_dispatched(row)
        transitional.append(row)
    monkeypatch.setattr(jobs.time, "sleep", cancel_while_waiting)
    store.executor = Mock()
    store._run(job.id, store._cancels[job.id])
    store.executor.assert_not_called()
    assert transitional and jobs._native_not_dispatched(json.loads(path.read_text()))
    # Restore the exact durable in-between cancelling observation, before the
    # runner had time to commit its final cancelled status.
    path.write_text(json.dumps(transitional[0]))
    store._resource_owner_handle.close()
    restored = factory()
    restored._restore_reservations_locked()
    assert not restored._external_held
