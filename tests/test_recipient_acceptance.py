"""Recipient-specific acceptance over real identity generations; synthetic DB only.

Covers A02/D28/FP-02 scoped withdrawal, A17 commit-time generation recheck,
D12/RC-03 recipient scope and A20/RC-07 order-independent replay. No compiler,
no corpus database, no catalog operation and no recovery credit.
"""
import itertools
import json
import sqlite3

import pytest

from agentdecompile_recovery.corpus import cross_place_admission as cpa
from agentdecompile_recovery.corpus import recipient_acceptance as ra

pytestmark = pytest.mark.unit

SHA = {name: (ch * 64) for name, ch in
       (('donor', 'a'), ('r1', 'b'), ('r2', 'c'), ('r3', 'd'), ('alt', 'e'))}
ADDR = 0x401000


def build_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        'CREATE TABLE binary (id INTEGER PRIMARY KEY, slug TEXT, content_sha256 TEXT);'
        'CREATE TABLE func (binary_id INTEGER, addr INTEGER, size INTEGER, return_type TEXT);'
        'CREATE TABLE identity (binary_id INTEGER, addr INTEGER, logical_id INTEGER, method TEXT,'
        ' evidence TEXT, confidence REAL);'
        'CREATE TABLE logical_function (id INTEGER PRIMARY KEY, name TEXT);'
        "INSERT INTO logical_function VALUES (1, 'Leaf');")
    for bid, key in enumerate(SHA, start=1):
        con.execute('INSERT INTO binary VALUES (?,?,?)', (bid, key, SHA[key]))
        con.execute("INSERT INTO func VALUES (?,?,6,'int')", (bid, ADDR))
        con.execute("INSERT INTO identity VALUES (?,?,1,'exact',?,0.9)",
                    (bid, ADDR, json.dumps({'dependencies': []})))
    con.commit()
    return con


@pytest.fixture
def con(tmp_path):
    connection = build_db(tmp_path / 'synthetic.sqlite')
    yield connection
    connection.close()


def dep(name):
    return ra.identity_dependency(SHA[name], ADDR)


def recipient(name, variant='x+2'):
    return {'binarySha256': SHA[name], 'address': ADDR, 'variant': variant}


def proposal(pid, target, roots, candidate='1', producer='producer-A'):
    return {'proposalId': pid, 'producer': producer, 'claimKind': 'recipient-local-match',
            'candidateSha256': candidate * 64, 'recipient': recipient(target),
            'rootSets': [[dep(n) for n in root] for root in roots], 'policyRevision': 'p1'}


def verification(target, verifier='verifier-B', outcome='pass', report='9'):
    return {'verifier': verifier, 'scope': recipient(target), 'outcome': outcome,
            'reportSha256': report * 64}


def reader(con):
    return lambda deps: ra.identity_generations(con, deps)


def touch(con, name):
    con.execute('UPDATE identity SET confidence=confidence+0.01 WHERE binary_id='
                '(SELECT id FROM binary WHERE slug=?)', (name,))
    con.commit()


def commit(con, ledger, prop, ver=None):
    target = {v: k for k, v in SHA.items()}[prop['recipient']['binarySha256']]
    return ra.commit(ledger, prop, ver or verification(target), reader(con))


def test_reader_uses_cross_place_identity_generation(con):
    con.row_factory = sqlite3.Row
    expected = cpa.identity_state(con, 1, ADDR)['generation']
    con.row_factory = None
    before = ra.identity_generations(con, [dep('donor')])
    assert before == {dep('donor'): expected}
    assert con.row_factory is None
    touch(con, 'donor')
    assert ra.identity_generations(con, [dep('donor')])[dep('donor')] != expected


def test_accepts_recipient_scoped_claim_with_current_generations(con):
    ledger, record = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]))
    assert record['outcome'] == 'accepted' and record['recoveryCredit'] is False
    assert set(record['dependencyVersions']) == {dep('r1'), dep('donor')}
    view = ra.state(ledger)
    assert view['current'][0]['selected'] == '1' * 64
    assert view['current'][0]['scope']['recipient'] == recipient('r1')


def test_producer_cannot_accept_own_proposal(con):
    ledger, record = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]),
                            verification('r1', verifier='producer-A'))
    assert record['outcome'] == 'rejected'
    assert 'verifier_not_independent_of_producer' in record['reasonCodes']
    assert ra.state(ledger)['current'] == []


def test_verification_scope_must_match_recipient(con):
    _, record = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]), verification('r2'))
    assert record['outcome'] == 'rejected'
    assert 'verification_scope_mismatch' in record['reasonCodes']


def test_donor_identity_only_root_cannot_accept_recipient(con):
    _, record = commit(con, (), proposal('P1', 'r2', [['donor']]))
    assert record['outcome'] == 'rejected'
    assert 'root_set_lacks_recipient_dependency' in record['reasonCodes']


def test_acceptance_for_one_recipient_gives_no_claim_for_sibling(con):
    ledger, _ = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]))
    assert ra.current_for(ledger, recipient('r1'), 'recipient-local-match')['selected'] == '1' * 64
    assert ra.current_for(ledger, recipient('r2'), 'recipient-local-match') is None
    assert ra.current_for(ledger, recipient('r1', variant='x+1'), 'recipient-local-match') is None


def test_generation_change_during_verification_rejects_commit(con):
    calls = []

    def racing(deps):
        calls.append(1)
        if len(calls) == 2:
            touch(con, 'donor')
        return ra.identity_generations(con, deps)
    ledger, record = ra.commit((), proposal('P1', 'r1', [['r1', 'donor']]),
                               verification('r1'), racing)
    assert len(calls) == 2
    assert record['outcome'] == 'stale'
    assert record['reasonCodes'] == ['dependency_generation_changed_during_verification']
    assert record['changedDependencies'] == [dep('donor')]
    assert ra.state(ledger)['current'] == [] and len(ledger) == 1


def test_missing_dependency_is_insufficient_evidence(con):
    con.execute("DELETE FROM identity WHERE binary_id=(SELECT id FROM binary WHERE slug='donor')")
    con.commit()
    _, record = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]))
    assert record['outcome'] == 'insufficient-evidence'
    assert record['dependencyVersions'][dep('donor')] is None


def test_commit_is_idempotent_for_current_acceptance(con):
    ledger, first = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]))
    again, second = commit(con, ledger, proposal('P1', 'r1', [['r1', 'donor']]))
    assert again == ledger and second == first


def test_withdraw_shared_root_retires_only_unsupported_descendants(con):
    ledger = ()
    ledger, p1 = commit(con, ledger, proposal('P1', 'r1', [['r1', 'donor']]))
    ledger, p2 = commit(con, ledger, proposal('P2', 'r2', [['r2', 'donor'], ['r2', 'alt']]))
    ledger, p3 = commit(con, ledger, proposal('P3', 'r3', [['r3']]))
    history = ledger
    touch(con, 'donor')
    ledger, withdrawal = ra.withdraw(ledger, dep('donor'), reader(con))
    assert withdrawal['retired'] == [p1['acceptanceId']]
    assert withdrawal['examined'] == sorted([p1['acceptanceId'], p2['acceptanceId']])
    assert ledger[:len(history)] == history  # immutable history retained
    current = {row['scope']['recipient']['binarySha256']: row for row in ra.state(ledger)['current']}
    assert set(current) == {SHA['r2'], SHA['r3']}
    assert current[SHA['r2']]['acceptanceIds'] == [p2['acceptanceId']]
    assert p3['acceptanceId'] in current[SHA['r3']]['acceptanceIds']


def test_update_away_and_back_does_not_revive_but_reacceptance_succeeds(con):
    ledger, old = commit(con, (), proposal('P1', 'r1', [['r1', 'donor']]))
    original = ra.identity_generations(con, [dep('donor')])
    con.execute("UPDATE identity SET method='changed' WHERE binary_id=1")
    con.commit()
    ledger, withdrawal = ra.withdraw(ledger, dep('donor'), reader(con))
    assert withdrawal['retired'] == [old['acceptanceId']]
    con.execute("UPDATE identity SET method='exact' WHERE binary_id=1")
    con.commit()
    assert ra.identity_generations(con, [dep('donor')]) == original
    assert ra.state(ledger)['current'] == []
    ledger, fresh = commit(con, ledger, proposal('P1', 'r1', [['r1', 'donor']]))
    assert fresh['outcome'] == 'accepted' and fresh['acceptanceId'] != old['acceptanceId']
    assert ra.state(ledger)['current'][0]['acceptanceIds'] == [fresh['acceptanceId']]


def test_contested_equal_support_stays_unresolved(con):
    ledger, a = commit(con, (), proposal('PA', 'r1', [['r1', 'donor']], candidate='1'))
    ledger, b = commit(con, ledger, proposal('PB', 'r1', [['r1', 'alt']], candidate='2'))
    row = ra.current_for(ledger, recipient('r1'), 'recipient-local-match')
    assert row['state'] == 'contested' and row['selected'] is None
    touch(con, 'alt')
    ledger, _ = ra.withdraw(ledger, dep('alt'), reader(con))
    row = ra.current_for(ledger, recipient('r1'), 'recipient-local-match')
    assert row['state'] == 'accepted' and row['selected'] == '1' * 64


def test_shuffled_completion_order_yields_identical_state(con):
    proposals = [proposal('PA', 'r1', [['r1', 'donor']], candidate='1'),
                 proposal('PB', 'r1', [['r1', 'alt']], candidate='2'),
                 proposal('PC', 'r2', [['r2', 'donor']], candidate='3'),
                 proposal('PD', 'r3', [['r3']], candidate='4')]
    views = set()
    for order in itertools.permutations(proposals):
        ledger = ()
        for prop in order:
            ledger, _ = commit(con, ledger, prop)
        views.add(ra.canonical(ra.state(ledger)))
    assert len(views) == 1


def test_replay_of_shuffled_records_is_identical(con):
    ledger = ()
    for prop in (proposal('PA', 'r1', [['r1', 'donor']]), proposal('PB', 'r2', [['r2', 'alt']])):
        ledger, _ = commit(con, ledger, prop)
    touch(con, 'donor')
    ledger, _ = ra.withdraw(ledger, dep('donor'), reader(con))
    expected = ra.canonical(ra.state(ledger))
    assert {ra.canonical(ra.state(order)) for order in itertools.permutations(ledger)} == {expected}


def test_malformed_proposal_is_refused():
    with pytest.raises(ValueError, match='invalid_proposal'):
        ra.commit((), {'proposalId': 'P1'}, {}, lambda deps: {})
