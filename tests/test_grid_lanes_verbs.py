"""Acceptance coverage for corpus-verb grid lanes and their task planner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdecompile_grid.core import NotConfigured, TaskSpec
from agentdecompile_grid.objects.local import LocalDirStore
from agentdecompile_recovery.corpus import cli as corpus_cli
from agentdecompile_recovery.corpus import logical, store
from agentdecompile_recovery.corpus.determinism_basis import basis_hash_for
from agentdecompile_recovery.corpus.extract import stamp_analyzer_identity
from agentdecompile_recovery.grid_lanes import splitter, verbs
from agentdecompile_recovery.grid_lanes._common import BasisRefused, ContentHashRefused, Infra, RunOutcome

pytestmark = pytest.mark.unit

ANALYZER = "test-analyzer"
HASH_A = "a" * 64
HASH_B = "b" * 64


def _store(
    path: Path,
    *,
    hashes: tuple[str | None, ...] = (HASH_A,),
    with_function: bool = False,
    stamp: bool = True,
) -> Path:
    con = store.connect(path)
    for binary_id, content_hash in enumerate(hashes, 1):
        con.execute(
            "INSERT INTO binary(id, repo_path, slug, language_id, content_sha256) VALUES (?,?,?,?,?)",
            (binary_id, f"/synthetic/{binary_id}", f"build-{binary_id}", "x86:LE:32:default", content_hash),
        )
    if with_function:
        con.execute(
            "INSERT INTO func(binary_id, addr, name, canon_key, canon_class, canon_method, canon_arity, "
            "name_origin, signature, plate, n_instr, n_blocks, cyclomatic, n_callees, strings, consts) "
            "VALUES (1,4096,'run','Widget::run','Widget','run',0,'plate','void run()','void run()',8,2,1,0,'[]','[]')"
        )
    if stamp:
        stamp_analyzer_identity(con, analyzer_version=ANALYZER)
    con.commit()
    con.close()
    return path


def _objects(path: Path) -> LocalDirStore:
    objects = LocalDirStore(path)
    # Corpus verbs mutate their scratch copy; keep the content-addressed input immutable.
    objects.get_path = lambda ref, dest: objects.materialize(ref, dest, link=False)  # type: ignore[method-assign]
    return objects


def _logical_spec(objects: LocalDirStore, db: Path, scratch: Path) -> TaskSpec:
    snapshot = splitter.snapshot_store(objects, db, scratch)
    assert snapshot.ref is not None
    return TaskSpec(
        kind=verbs.CorpusLogicalBuild.name,
        kind_version=verbs.CorpusLogicalBuild.version,
        inputs={"store": snapshot.ref},
        params={},
        basis_hash=basis_hash_for(ANALYZER),
        capabilities=verbs.CorpusLogicalBuild.capabilities,
        budget=verbs.CorpusLogicalBuild.budget,
    )


def _run_logical_in_process(argv, *, cwd, timeout_s, env) -> RunOutcome:
    """Exercise the real logical builder without paying for a second Python startup."""
    con = store.connect(Path(cwd) / verbs.STORE_FILENAME)
    try:
        summary = logical.build(con)
    except Exception as exc:
        line = corpus_cli._refusal_line(exc)
        if line is None:
            raise
        return RunOutcome(tuple(argv), 2, "", line + "\n", 0.01, False)
    finally:
        con.close()
    return RunOutcome(tuple(argv), 0, json.dumps(summary) + "\n", "", 0.01, False)


def test_verb_refusal_is_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mixed = _store(tmp_path / "mixed.sqlite", hashes=(HASH_A, HASH_B))
    con = store.connect(mixed)
    con.execute("UPDATE binary SET basis_hash=? WHERE id=2", ("f" * 64,))
    con.commit()
    con.close()
    objects = _objects(tmp_path / "objects-mixed")

    with pytest.raises(BasisRefused, match="mixed basis_hash"):
        verbs.CorpusLogicalBuild.plan(objects, mixed)
    assert len(list(objects.list())) == 1, "a basis refusal may publish only its immutable input snapshot"

    missing = _store(tmp_path / "missing.sqlite", hashes=(None,), with_function=True)
    missing_objects = _objects(tmp_path / "objects-missing")
    spec = _logical_spec(missing_objects, missing, tmp_path / "missing-snapshot")
    before = list(missing_objects.list())
    monkeypatch.setattr(verbs, "run_argv", _run_logical_in_process)
    with pytest.raises(ContentHashRefused) as caught:
        verbs.CorpusLogicalBuild().run(spec, missing_objects, str(tmp_path / "missing-run"))
    assert "build-1" not in caught.value.reason
    assert before == list(missing_objects.list()), "content-hash refusal must not publish verb outputs"


def test_verb_kind_task_id_stable(tmp_path: Path) -> None:
    db = _store(tmp_path / "stable.sqlite", with_function=True)
    first = verbs.CorpusLogicalBuild.plan(_objects(tmp_path / "node-a"), db)
    second = verbs.CorpusLogicalBuild.plan(_objects(tmp_path / "node-b"), db)

    assert [task.task_id for task in first] == [task.task_id for task in second]
    assert [task.inputs for task in first] == [task.inputs for task in second]


def test_verb_receipt_portable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _store(tmp_path / "portable.sqlite", with_function=True)
    objects = _objects(tmp_path / "objects")
    spec = _logical_spec(objects, db, tmp_path / "snapshot")
    monkeypatch.setattr(verbs, "run_argv", _run_logical_in_process)

    result = verbs.CorpusLogicalBuild().run(spec, objects, str(tmp_path / "run"))
    receipt = json.loads(objects.get(result.outputs["receipt"]))
    encoded = json.dumps(receipt, sort_keys=True)

    assert str(tmp_path) not in encoded
    assert "build-1" not in encoded
    assert receipt["store"] == str(spec.inputs["store"])


def test_verb_timeout_is_infra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _store(tmp_path / "timeout.sqlite", with_function=True)
    objects = _objects(tmp_path / "objects")
    spec = _logical_spec(objects, db, tmp_path / "snapshot")
    before = list(objects.list())

    monkeypatch.setattr(
        verbs,
        "run_argv",
        lambda *args, **kwargs: RunOutcome(("synthetic",), -15, "", "", 0.01, True),
    )
    with pytest.raises(Infra, match="timeout:logical-build"):
        verbs.CorpusLogicalBuild().run(spec, objects, str(tmp_path / "run"))

    assert before == list(objects.list()), "a timeout must not publish a receipt or output object"


def test_logical_rows_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _store(tmp_path / "logical.sqlite", with_function=True)
    objects = _objects(tmp_path / "objects")
    spec = _logical_spec(objects, db, tmp_path / "snapshot")
    kind = verbs.CorpusLogicalBuild()
    monkeypatch.setattr(verbs, "run_argv", _run_logical_in_process)

    first = kind.run(spec, objects, str(tmp_path / "run-a"))
    second = kind.run(spec, objects, str(tmp_path / "run-b"))

    assert first.outputs["logical_rows"] == second.outputs["logical_rows"]
    payload = json.loads(objects.get(first.outputs["logical_rows"]))
    assert payload["logical_function"][0]["canon_key"] == "Widget::run"
    assert payload["identity"][0]["binary"] == HASH_A


def test_attest_declared(tmp_path: Path) -> None:
    description = verbs.CorpusAttest.describe()
    assert description["status"] == "declared"
    assert description["kind"] == "corpus-attest"
    objects = _objects(tmp_path / "objects")
    store_ref = objects.put(b"synthetic store placeholder")
    spec = TaskSpec(
        kind="corpus-attest",
        kind_version=verbs.CorpusAttest.version,
        inputs={"store": store_ref},
        params={"verb": "logical-build", "deadline_s": 1.0},
        basis_hash="d" * 64,
    )

    with pytest.raises(NotConfigured, match="U28x"):
        verbs.CorpusAttest().run(spec, objects, str(tmp_path / "run"))


def test_plan_backfill_analyzer_identity_with_null_identity(tmp_path: Path) -> None:
    db = _store(tmp_path / "repair.sqlite", stamp=False)
    objects = _objects(tmp_path / "objects")

    tasks = splitter.plan_tasks(
        "corpus-backfill-pass",
        db,
        None,
        512,
        objects=objects,
        passes=["analyzer_identity"],
    )

    assert len(tasks) == 1
    assert tasks[0].params["pass"] == "analyzer_identity"
    assert tasks[0].basis_hash == splitter.repair_basis_hash("corpus-backfill-pass")
    assert tasks[0].inputs["store"] in list(objects.list())
