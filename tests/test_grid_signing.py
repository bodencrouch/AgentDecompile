"""Signing, chain and trust tests for ``agentdecompile_grid`` (review findings #1 and #4).

The four ``signing-*`` acceptance tests are the ones named in ``log/signing.py``'s docstring.
The rest prove that readers verify signatures against a trusted keyring before they fold,
index or apply a record: ``frontier.derive``, ``worker.records`` (``proposal_from_record`` and
``LogTaskIndex``), ``SQLiteViewApplier``, checkpoints, and ``worker.agent.join``'s invite.

New names are imported inside the test bodies so a missing name fails one test, not collection.
All key material here is generated per test under ``tmp_path``; nothing touches the network.
"""
from __future__ import annotations

import dataclasses
import shutil
import sqlite3
from pathlib import Path

import pytest

from agentdecompile_grid.core import (
    SIGNERS,
    NodeIdentity,
    NotConfigured,
    ObjectRef,
    RecordType,
    ResultStatus,
    TaskResult,
    TaskSpec,
    canonical_json,
)
from agentdecompile_grid.log import signing
from agentdecompile_grid.log.records import (
    EMPTY_HEAD,
    BadSignature,
    ChainBroken,
    Draft,
    UnknownSigner,
    build_record,
    head_of,
    seal,
    verify_chain,
)
from agentdecompile_grid.worker import identity as ident

HMAC_TEST_SECRET = b"grid-test-only-secret-0123456789"   # test value, never a real secret
NOW = 1_800_000_000.0
BASIS = "basis-test"


# --------------------------------------------------------------------------- in-memory stores
class MemLog:
    """A LogStore good enough for readers: records are sealed here with any signer."""

    name = "mem"

    def __init__(self) -> None:
        self._parts: dict[str, list] = {}

    def add(self, partition: str, rtype: RecordType, body: dict, signer, *, validate: bool = True):
        run = self._parts.setdefault(partition, [])
        record = seal(partition, [Draft(rtype, body)], head_of(run), signer, validate=validate)[0]
        run.append(record)
        return record

    def read(self, partition: str, since_seq: int = 0):
        return iter([r for r in self._parts.get(partition, []) if r.seq > since_seq])

    def partitions(self):
        return iter(sorted(self._parts))

    def last_seq(self, partition: str) -> int:
        run = self._parts.get(partition, [])
        return run[-1].seq if run else 0


class MemObjects:
    name = "mem"

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put(self, data: bytes) -> ObjectRef:
        ref = ObjectRef.of_bytes(data)
        self._data[str(ref)] = data
        return ref

    def get(self, ref) -> bytes:
        return self._data[str(ref)]

    def exists(self, ref) -> bool:
        return str(ref) in self._data


# --------------------------------------------------------------------------- scenario
def _node(tmp_path: Path, name: str) -> tuple[ident.NodeKey, ident.NodeSigner]:
    key = ident.NodeKeyStore(tmp_path / "nodes" / name).create(algorithm="ed25519", now=NOW)
    return key, ident.NodeSigner(key)


class Grid:
    """An operator (ed25519 signer), a worker W and a verifier V (node keys), and Mallory M,
    whose key is in nobody's keyring.  ``trusted`` holds the operator, W and V."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.operator = signing.Ed25519Signer.generate(tmp_path / "operator")
        self.w_key, self.w = _node(tmp_path, "worker")
        self.v_key, self.v = _node(tmp_path, "verifier")
        self.m_key, self.m = _node(tmp_path, "mallory")
        trusted_dir = tmp_path / "trusted"
        trusted_dir.mkdir()
        shutil.copy(tmp_path / "operator" / "ed25519.pub", trusted_dir / "operator.pub")
        shutil.copy(tmp_path / "nodes" / "worker" / "keys" / "node.json", trusted_dir / "worker.json")
        shutil.copy(tmp_path / "nodes" / "verifier" / "keys" / "node.json", trusted_dir / "verifier.json")
        self.trusted_dir = trusted_dir
        self.log = MemLog()
        self.objects = MemObjects()

    def keyring(self):
        ring = signing.Keyring()
        ring.load_dir(self.trusted_dir)
        return ring

    def spec(self, n: int, partition: str = "demo") -> TaskSpec:
        return TaskSpec(kind="demo", kind_version=1, inputs={}, params={"n": n}, basis_hash=BASIS, partition=partition)

    def publish(self, spec: TaskSpec, signer=None):
        return self.log.add(spec.partition_key, RecordType.TASK, spec.to_record(), signer or self.operator)

    def propose(self, spec: TaskSpec, signer, key_id: str) -> ObjectRef:
        result = TaskResult(spec.task_id, ResultStatus.OK, {}, key_id, BASIS, 0.1)
        ref = self.objects.put(canonical_json(result.to_record()))
        self.log.add(spec.partition_key, RecordType.RESULT,
                     {"task_id": spec.task_id, "result_ref": str(ref), "producer_key": key_id, "status": "ok"}, signer)
        return ref

    def verified(self, spec: TaskSpec, ref: ObjectRef, signer, *, verifier_key: str, producer_key: str, validate: bool = True):
        body = {"task_id": spec.task_id, "result_ref": str(ref), "outcome": "verified", "verifier_key": verifier_key,
                "method": "recompute", "producer_key": producer_key, "evidence": {}}
        return self.log.add(spec.partition_key, RecordType.VERIFIED, body, signer, validate=validate)


@pytest.fixture()
def grid(tmp_path: Path) -> Grid:
    return Grid(tmp_path)


# =========================================================================== signing-* (named in signing.py)
def test_signing_roundtrip(tmp_path: Path) -> None:
    """signing-roundtrip: each signer's sealed record verifies through a keyring holding only the
    public part, and fails after flipping one body byte."""
    ed = signing.Ed25519Signer.generate(tmp_path / "ed")
    hm = signing.HMACSigner(HMAC_TEST_SECRET, label="node-a")
    cases = []
    ring = signing.Keyring(allow_null=True)
    cases.append((signing.NullSigner(label="lap"), ring))
    ring = signing.Keyring()
    ring.add_hmac_secret(HMAC_TEST_SECRET)          # the hmac "public part" is the shared secret (stated trust model)
    cases.append((hm, ring))
    ring = signing.Keyring()
    ring.add_ed25519_public(ed.public_bytes)        # public bytes only; no private key in this keyring
    cases.append((ed, ring))
    for signer, keyring in cases:
        record = build_record("demo", 1, RecordType.NOTE, {"note": "hello", "n": 1}, "", signer)
        signing.verify_record(record, keyring)
        flipped = dataclasses.replace(record, body={"note": "hellp", "n": 1})
        with pytest.raises(BadSignature):
            signing.verify_record(flipped, keyring)


def test_signing_null_policy() -> None:
    """signing-null-policy: a null-signed record is refused by a keyring without allow_null."""
    record = build_record("demo", 1, RecordType.NOTE, {"n": 1}, "", signing.NullSigner())
    with pytest.raises(UnknownSigner, match="null"):
        signing.verify_record(record, signing.Keyring())
    signing.verify_record(record, signing.Keyring(allow_null=True))


def test_signing_hmac_labels() -> None:
    """signing-hmac-labels: two labels under one secret have different key ids and verify each other."""
    a = signing.HMACSigner(HMAC_TEST_SECRET, label="a")
    b = signing.HMACSigner(HMAC_TEST_SECRET, label="b")
    assert a.key_id != b.key_id
    data = b"canonical bytes"
    assert a.verify(b.key_id, data, b.sign(data))
    assert b.verify(a.key_id, data, a.sign(data))
    assert not a.verify(b.key_id, data + b"x", b.sign(data))


def test_signing_ed25519_declared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """signing-ed25519-declared: without cryptography, generate raises NotConfigured naming the
    package, and SIGNERS still lists ed25519."""
    monkeypatch.setattr(signing, "HAVE_CRYPTOGRAPHY", False)
    with pytest.raises(NotConfigured, match="cryptography"):
        signing.Ed25519Signer.generate(tmp_path / "ed")
    assert "ed25519" in SIGNERS
    assert signing.Ed25519Signer.describe()["status"] == "declared"


# =========================================================================== verify_chain
def test_verify_chain_batch_of_64_with_keyring(tmp_path: Path) -> None:
    """U122 (c)+(d): 64 sealed records verify offline with a keyring and return the live head."""
    ed = signing.Ed25519Signer.generate(tmp_path / "ed")
    ring = signing.Keyring()
    ring.add_ed25519_public(ed.public_bytes)
    drafts = [Draft(RecordType.NOTE, {"i": i}) for i in range(64)]
    run = seal("demo", drafts, EMPTY_HEAD, ed)
    assert verify_chain(run, verifier=ring) == head_of(run) == (64, run[-1].digest())


def test_verify_chain_refuses_by_name(tmp_path: Path) -> None:
    """A tampered body, a foreign key, a broken prev and a seq gap are each refused by name."""
    ed = signing.Ed25519Signer.generate(tmp_path / "ed")
    other = signing.Ed25519Signer.generate(tmp_path / "other")
    ring = signing.Keyring()
    ring.add_ed25519_public(ed.public_bytes)
    run = seal("demo", [Draft(RecordType.NOTE, {"i": i}) for i in range(4)], EMPTY_HEAD, ed)

    tampered = list(run)
    tampered[2] = dataclasses.replace(run[2], body={"i": 99})
    with pytest.raises(BadSignature, match="demo'#3"):
        verify_chain(tampered[:3], verifier=ring)

    foreign = seal("demo", [Draft(RecordType.NOTE, {"i": 0})], EMPTY_HEAD, other)
    with pytest.raises(BadSignature):
        verify_chain(foreign, verifier=ring)

    relinked = [run[0], dataclasses.replace(run[1], prev="0" * 64)]
    with pytest.raises(ChainBroken, match="prev"):
        verify_chain(relinked, verifier=ring)

    with pytest.raises(ChainBroken, match="seq"):
        verify_chain([run[0], run[2]], verifier=ring)


# =========================================================================== keyring: node keys and roles
def test_keyring_verifies_node_keys_from_trusted_dir(grid: Grid) -> None:
    """Workers sign with node keys (32-hex ids, b64 signatures); the trusted dir holds their
    public records.  A record by W verifies; Mallory is unknown; a mislabelled record is refused."""
    ring = grid.keyring()
    assert ring.knows(grid.w_key.key_id) and ring.knows(grid.v_key.key_id)
    assert not ring.knows(grid.m_key.key_id)
    good = build_record("demo", 1, RecordType.NOTE, {"n": 1}, "", grid.w)
    signing.verify_record(good, ring)
    with pytest.raises(UnknownSigner):
        signing.verify_record(build_record("demo", 1, RecordType.NOTE, {"n": 1}, "", grid.m), ring)
    with pytest.raises(BadSignature):
        signing.verify_record(dataclasses.replace(good, body={"n": 2}), ring)

    bad_dir = grid.tmp / "bad-trusted"
    bad_dir.mkdir()
    text = (grid.trusted_dir / "worker.json").read_text("utf-8").replace(grid.w_key.key_id, grid.m_key.key_id)
    (bad_dir / "liar.json").write_text(text, "utf-8")
    with pytest.raises(signing.KeyMaterialError, match="liar.json"):
        signing.Keyring().load_dir(bad_dir)


def test_keyring_missing_dir_is_empty_not_a_crash(tmp_path: Path) -> None:
    ring = signing.Keyring.from_locator({"allow_null": False, "key_dir": str(tmp_path / "absent")})
    assert list(ring.key_ids()) == [] and not ring.allow_null


def test_task_must_be_signed_by_an_operator_key(grid: Grid) -> None:
    """A TASK by a trusted *node* key is refused by name; the operator's TASK is accepted."""
    from agentdecompile_grid.log.records import SignerNotAuthorized

    ring = grid.keyring()
    by_operator = grid.publish(grid.spec(1))
    signing.authorize_record(by_operator, ring)
    by_worker = grid.publish(grid.spec(2), signer=grid.w)
    signing.verify_record(by_worker, ring)          # the signature itself is fine
    with pytest.raises(SignerNotAuthorized, match="operator"):
        signing.authorize_record(by_worker, ring)


# =========================================================================== frontier
def test_frontier_accepts_properly_signed_records(grid: Grid) -> None:
    from agentdecompile_grid.log import frontier

    spec = grid.spec(1)
    grid.publish(spec)
    ref = grid.propose(spec, grid.w, grid.w_key.key_id)
    grid.verified(spec, ref, grid.v, verifier_key=grid.v_key.key_id, producer_key=grid.w_key.key_id)
    report = frontier.derive(grid.log, grid.objects, NOW, keyring=grid.keyring())
    assert report.done == (spec.task_id,)
    assert report.untrusted == ()


def test_frontier_refuses_foreign_task_and_verified(grid: Grid) -> None:
    """Mallory's VERIFIED does not make a task done, Mallory's TASK is never offered, and a TASK
    by a node key is not offered either; each refusal is named on the report."""
    from agentdecompile_grid.log import frontier

    spec = grid.spec(1)
    grid.publish(spec)
    ref = grid.propose(spec, grid.w, grid.w_key.key_id)
    forged = grid.verified(spec, ref, grid.m, verifier_key=grid.m_key.key_id, producer_key=grid.w_key.key_id)
    foreign_task = grid.publish(grid.spec(2, partition="other"), signer=grid.m)
    node_task = grid.publish(grid.spec(3, partition="other"), signer=grid.w)

    report = frontier.derive(grid.log, grid.objects, NOW, keyring=grid.keyring())
    assert spec.task_id not in report.done
    assert report.awaiting_verification == (spec.task_id,)
    assert [s.task_id for s in report.ready] == [spec.task_id]      # still offered: only W's proposal counts
    assert set(report.untrusted) == {
        ("demo", forged.seq, "unknown-signer"),
        ("other", foreign_task.seq, "unknown-signer"),
        ("other", node_task.seq, "signer-not-authorized"),
    }
    # a later trusted record still folds: the refusal does not stall the partition
    ok = grid.publish(grid.spec(4, partition="other"))
    report = frontier.derive(grid.log, grid.objects, NOW, keyring=grid.keyring())
    assert {s.task_id for s in report.ready} == {spec.task_id, TaskSpec.from_record(ok.body).task_id}


def test_frontier_without_keyring_fails_closed(grid: Grid) -> None:
    from agentdecompile_grid.log import frontier

    spec = grid.spec(1)
    grid.publish(spec)
    report = frontier.derive(grid.log, grid.objects, NOW)
    assert report.ready == () and report.untrusted == (("demo", 1, "unknown-signer"),)


def test_latest_checkpoint_ignores_untrusted_checkpoint(grid: Grid) -> None:
    from agentdecompile_grid.log import compaction
    from agentdecompile_grid.log.frontier import PartitionState

    spec = grid.spec(1)
    grid.publish(spec)
    fake = compaction.CheckpointSummary.from_state(PartitionState("demo"))
    grid.objects.put(fake.bytes)
    grid.log.add("demo", RecordType.CHECKPOINT, fake.body(), grid.m)
    assert compaction.latest_checkpoint(grid.log, grid.objects, "demo", keyring=grid.keyring()) is None


# =========================================================================== worker readers
def test_proposals_and_task_index_refuse_foreign_signer(grid: Grid) -> None:
    from agentdecompile_grid.worker import records

    ring = grid.keyring()
    spec = grid.spec(1)
    grid.publish(spec)
    grid.propose(spec, grid.w, grid.w_key.key_id)
    grid.propose(spec, grid.m, grid.m_key.key_id)
    foreign = grid.spec(2)
    grid.publish(foreign, signer=grid.m)

    refused: list = []
    proposals = records.read_results(grid.log, "demo", keyring=ring, refused=refused)
    assert [p.producer_key for p in proposals] == [grid.w_key.key_id]
    assert refused == [("demo", 3, "unknown-signer")]

    index = records.LogTaskIndex(grid.log, keyring=ring)
    assert index.task(spec.task_id) == spec
    assert index.task(foreign.task_id) is None
    assert ("demo", 4, "unknown-signer") in index.refused


# =========================================================================== view applier
def _rows(grid: Grid) -> list[tuple]:
    con = sqlite3.connect(str(grid.tmp / "view.db"))
    try:
        return con.execute("SELECT task_id, verifier_key FROM grid_results").fetchall()
    finally:
        con.close()


def test_applier_applies_properly_signed_verified(grid: Grid) -> None:
    spec = grid.spec(1)
    grid.publish(spec)
    ref = grid.propose(spec, grid.w, grid.w_key.key_id)
    grid.verified(spec, ref, grid.v, verifier_key=grid.v_key.key_id, producer_key=grid.w_key.key_id)
    from agentdecompile_grid.view.applier import SQLiteViewApplier

    applier = SQLiteViewApplier(grid.tmp / "view.db", "demo", keyring=grid.keyring())
    try:
        applied = applier.apply(grid.log.read("demo"), grid.objects)
    finally:
        applier.close()
    assert applied == 3
    assert _rows(grid) == [(spec.task_id, grid.v_key.key_id)]


@pytest.mark.parametrize("case", ["foreign-verified", "foreign-task", "self-verified", "verifier-not-signer"])
def test_applier_refuses_untrusted_verified_or_task(grid: Grid, case: str) -> None:
    """Every refusal is the named ViewUntrusted, the position stays before the record, and no
    grid_results row lands."""
    from agentdecompile_grid.view.applier import ViewUntrusted

    spec = grid.spec(1)
    if case == "foreign-task":
        bad = grid.publish(spec, signer=grid.m)
        reason = "unknown-signer"
    else:
        grid.publish(spec)
        ref = grid.propose(spec, grid.w, grid.w_key.key_id)
        if case == "foreign-verified":
            bad = grid.verified(spec, ref, grid.m, verifier_key=grid.m_key.key_id, producer_key=grid.w_key.key_id)
            reason = "unknown-signer"
        elif case == "self-verified":
            bad = grid.verified(spec, ref, grid.w, verifier_key=grid.w_key.key_id, producer_key=grid.w_key.key_id)
            reason = "not-independent"
        else:   # V signs a body that names W as the verifier (validate=False: the append path would refuse it)
            bad = grid.verified(spec, ref, grid.v, verifier_key=grid.w_key.key_id, producer_key=grid.w_key.key_id, validate=False)
            reason = "verifier-not-signer"
    from agentdecompile_grid.view.applier import SQLiteViewApplier

    applier = SQLiteViewApplier(grid.tmp / "view.db", "demo", keyring=grid.keyring())
    try:
        with pytest.raises(ViewUntrusted, match=reason) as info:
            applier.apply(grid.log.read("demo"), grid.objects)
        assert info.value.seq == bad.seq
        assert applier.position() == {"demo": bad.seq - 1}
        assert applier.state()["state"].startswith("view-stale: untrusted")
    finally:
        applier.close()
    assert _rows(grid) == []


def test_materialize_reports_untrusted_partition_by_name(grid: Grid) -> None:
    from agentdecompile_grid.view.applier import materialize

    spec = grid.spec(1)
    grid.publish(spec, signer=grid.m)
    report = materialize(grid.tmp, grid.tmp / "view.db", objects=grid.objects, log=grid.log, keyring=grid.keyring())
    assert report["stale"] == ["demo"]
    assert "ViewUntrusted" in report["partitions"]["demo"]["state"]


# =========================================================================== invites and join
def _operator_invite(tmp_path: Path, name: str = "issuer"):
    key = ident.NodeKeyStore(tmp_path / name).create(algorithm="ed25519", now=NOW)
    issuer = NodeIdentity(key.key_id, (), (), role="operator")
    invite = ident.make_invite(f"file://{tmp_path}/g/fabric1", "fleet", issuer, ident.NodeSigner(key), now=NOW)
    return key, invite


def test_join_rejects_self_signed_invite_from_unknown_issuer(tmp_path: Path) -> None:
    """Anyone can mint a well-formed invite carrying its own public key.  ``join`` must refuse
    it by name before it creates a key, takes a lock or touches an endpoint."""
    from agentdecompile_grid.worker import agent

    _key, invite = _operator_invite(tmp_path)
    state_dir = tmp_path / "joiner"
    endpoint = agent.Endpoint("unix", path=str(tmp_path / "s.sock"))
    with pytest.raises(ident.InviteError, match="trusted keyring"):
        agent.join(invite.url(), state_dir=state_dir, endpoint=endpoint, env={}, wall=lambda: NOW,
                   keyring=signing.Keyring(), derive=lambda *a: None)
    assert not state_dir.exists()
    assert not (tmp_path / "s.sock.lock").exists()


def test_invite_issuer_must_be_pinned(tmp_path: Path) -> None:
    """``parse_invite_url`` no longer trusts the issuer key carried in the token; a pinned issuer
    verifies, and a pinned key whose role differs from the invite's claim is refused."""
    key, invite = _operator_invite(tmp_path)
    joiner = ident.NodeSigner(ident.NodeKeyStore(tmp_path / "j").create(algorithm="ed25519", now=NOW))
    with pytest.raises(ident.InviteError, match="unknown issuer"):
        ident.parse_invite_url(invite.url(), now=NOW, verifier=joiner)

    ring = signing.Keyring()
    ring.add_node_key(key, role="operator")
    ident.verify_invite(invite, ring)
    demoted = signing.Keyring()
    demoted.add_node_key(key, role="donor")
    with pytest.raises(ident.InviteError, match="role"):
        ident.verify_invite(invite, demoted)
    tampered = dataclasses.replace(invite, role="operator")
    with pytest.raises(ident.InviteError, match="does not verify"):
        ident.verify_invite(tampered, ring)


def test_grid_config_keyring_defaults_refuse_null() -> None:
    """Null signatures are an explicit opt-in: the default GridConfig keyring does not allow them."""
    from agentdecompile_grid.config import GridConfig

    assert GridConfig().keyring_locator()["allow_null"] is False
