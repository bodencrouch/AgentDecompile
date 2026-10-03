"""Recipient-specific acceptance records over observed dependency generations.

Records in, state out. A producer proposes a candidate for one exact recipient
(binary content, address, variant); a separate verifier supplies its recipient-local
observation. Acceptance binds every root-set dependency to the generation read at
evaluation and rechecks that basis just before appending (design section
"Acceptance record field"; A17). Withdrawal is scoped: it examines only current
acceptances that name the changed dependency and retires those without another
intact root set (A02). A retired acceptance never revives, even when the dependency
returns to identical content; a new acceptance record is required. State depends
only on the set of records, so shuffled completion or replay order is irrelevant (A20).

This module grants no recovery credit and writes no corpus state. The only
generation reader provided here is the cross-place identity-graph digest.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
import re
import sqlite3

SCHEMA = 'agentdecompile.recipient-acceptance/v1'
_HEX = re.compile(r'[0-9a-f]{64}')
_DEP = re.compile(r'identity:([0-9a-f]{64}):([0-9]+)')
Reader = Callable[[list], Mapping]


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identity_dependency(binary_sha256: str, address: int) -> str:
    return f'identity:{binary_sha256}:{address}'


def identity_generations(con: sqlite3.Connection, dependencies) -> dict:
    """Read cross-place identity generations; unreadable dependencies map to None."""
    from .cross_place_admission import identity_state
    previous, con.row_factory = con.row_factory, sqlite3.Row
    try:
        result = {}
        for dep in sorted(set(dependencies)):
            match = _DEP.fullmatch(dep)
            generation = None
            if match:
                rows = con.execute('SELECT id FROM binary WHERE content_sha256=?', (match[1],)).fetchall()
                if len(rows) == 1:
                    try:
                        generation = identity_state(con, int(rows[0][0]), int(match[2]))['generation']
                    except (ValueError, sqlite3.Error):
                        generation = None
            result[dep] = generation
        return result
    finally:
        con.row_factory = previous


def _scope(value) -> bool:
    return (type(value) is dict and set(value) == {'binarySha256', 'address', 'variant'}
            and isinstance(value['binarySha256'], str) and _HEX.fullmatch(value['binarySha256'])
            and type(value['address']) is int and value['address'] >= 0
            and isinstance(value['variant'], str) and 0 < len(value['variant']) <= 64)


def _validate(proposal, verification):
    fields = {'proposalId', 'producer', 'claimKind', 'candidateSha256', 'recipient',
              'rootSets', 'policyRevision'}
    roots = proposal.get('rootSets') if type(proposal) is dict else None
    if (type(proposal) is not dict or set(proposal) != fields
            or any(not isinstance(proposal[k], str) or not proposal[k]
                   for k in ('proposalId', 'producer', 'claimKind', 'policyRevision'))
            or not isinstance(proposal['candidateSha256'], str)
            or not _HEX.fullmatch(proposal['candidateSha256'])
            or not _scope(proposal['recipient'])
            or type(roots) is not list or not 0 < len(roots) <= 16
            or any(type(r) is not list or not 0 < len(r) <= 64
                   or any(not isinstance(d, str) or not _DEP.fullmatch(d) for d in r) for r in roots)):
        raise ValueError('invalid_proposal')
    if (type(verification) is not dict
            or set(verification) != {'verifier', 'scope', 'outcome', 'reportSha256'}
            or not isinstance(verification['verifier'], str) or not verification['verifier']
            or verification['outcome'] not in ('pass', 'fail')
            or not isinstance(verification['reportSha256'], str)
            or not _HEX.fullmatch(verification['reportSha256'])):
        raise ValueError('invalid_verification')


def _dependencies(record) -> list:
    return sorted({d for root in record['rootSets'] for d in root})


def _intact(record, current: Mapping) -> list:
    versions = record['dependencyVersions']
    return [i for i, root in enumerate(record['rootSets'])
            if all(versions.get(d) is not None and current.get(d) == versions[d] for d in root)]


def commit(ledger: tuple, proposal: dict, verification: dict, read: Reader):
    """Evaluate outside the append, recheck the basis, then append one record.

    Returns ``(ledger, record)``. Rejections are retained as negative records.
    A matching current acceptance is returned unchanged (idempotency).
    """
    _validate(proposal, verification)
    ledger = tuple(ledger)
    key = digest({'proposal': proposal, 'claimKind': proposal['claimKind'],
                  'policyRevision': proposal['policyRevision']})
    retired = _retired(ledger)
    for record in ledger:
        if record.get('idempotencyKey') == key and record['kind'] == 'acceptance' \
                and record['acceptanceId'] not in retired:
            return ledger, record
    deps = _dependencies(proposal)
    first = read(deps)
    basis = {d: first.get(d) for d in deps}
    recipient_dep = identity_dependency(proposal['recipient']['binarySha256'],
                                        proposal['recipient']['address'])
    reasons = []
    if verification['verifier'] == proposal['producer']:
        reasons.append('verifier_not_independent_of_producer')
    if verification['scope'] != proposal['recipient']:
        reasons.append('verification_scope_mismatch')
    if verification['outcome'] != 'pass':
        reasons.append('recipient_verification_failed')
    if any(recipient_dep not in root for root in proposal['rootSets']):
        reasons.append('root_set_lacks_recipient_dependency')
    body = {'schema': SCHEMA, 'idempotencyKey': key, 'proposalId': proposal['proposalId'],
            'producer': proposal['producer'], 'claimKind': proposal['claimKind'],
            'claimScope': proposal['recipient'], 'candidateSha256': proposal['candidateSha256'],
            'policyRevision': proposal['policyRevision'], 'rootSets': proposal['rootSets'],
            'verifierIdentity': verification['verifier'], 'reportSha256': verification['reportSha256'],
            'dependencyVersions': basis, 'recoveryCredit': False}
    satisfied = _intact(body, basis)
    if reasons:
        outcome = 'rejected'
    elif not satisfied:
        outcome, reasons = 'insufficient-evidence', ['no_root_set_with_readable_generations']
    else:
        outcome = 'accepted'
    if outcome == 'accepted':
        recheck = read(deps)
        changed = sorted(d for d in deps if recheck.get(d) != basis[d])
        if changed:
            outcome, reasons = 'stale', ['dependency_generation_changed_during_verification']
            body['changedDependencies'] = changed
    body.update(outcome=outcome, reasonCodes=reasons, satisfiedRootSets=satisfied)
    if outcome == 'accepted':
        ordinal = sum(1 for r in ledger if r.get('idempotencyKey') == key and r['kind'] == 'acceptance')
        record = {'kind': 'acceptance', **body, 'ordinal': ordinal,
                  'acceptanceId': digest({'key': key, 'ordinal': ordinal, 'basis': basis})}
    else:
        record = {'kind': 'refusal', **body, 'recordId': digest(body)}
    return ledger + (record,), record


def _retired(ledger) -> set:
    return {i for r in ledger if r['kind'] == 'withdrawal' for i in r['retired']}


def withdraw(ledger: tuple, dependency: str, read: Reader):
    """Scoped recheck after ``dependency`` changed; retire claims with no intact root."""
    if not isinstance(dependency, str) or not _DEP.fullmatch(dependency):
        raise ValueError('invalid_dependency')
    ledger, retired = tuple(ledger), _retired(ledger)
    scoped = sorted((r for r in ledger if r['kind'] == 'acceptance'
                     and r['acceptanceId'] not in retired and dependency in _dependencies(r)),
                    key=lambda r: r['acceptanceId'])
    deps = sorted({d for r in scoped for d in _dependencies(r)})
    current = dict(read(deps)) if deps else {}
    observed = {d: current.get(d) for d in deps}
    body = {'schema': SCHEMA, 'kind': 'withdrawal', 'dependency': dependency,
            'observed': observed, 'examined': [r['acceptanceId'] for r in scoped],
            'retired': [r['acceptanceId'] for r in scoped if not _intact(r, observed)],
            'reasonCodes': ['no_intact_independent_root_set']}
    record = {**body, 'recordId': digest(body)}
    return ledger + (record,), record


def state(ledger) -> dict:
    """Derive current claims from the record set; order never changes the result."""
    retired = _retired(ledger)
    groups = {}
    for record in ledger:
        if record['kind'] == 'acceptance' and record['acceptanceId'] not in retired:
            scope = {'recipient': record['claimScope'], 'claimKind': record['claimKind']}
            entry = groups.setdefault(canonical(scope), {'scope': scope, 'ids': set(), 'cands': set()})
            entry['ids'].add(record['acceptanceId'])
            entry['cands'].add(record['candidateSha256'])
    current = []
    for _, entry in sorted(groups.items()):
        candidates = sorted(entry['cands'])
        contested = len(candidates) > 1
        current.append({'scope': entry['scope'], 'acceptanceIds': sorted(entry['ids']),
                        'candidates': candidates, 'state': 'contested' if contested else 'accepted',
                        'selected': None if contested else candidates[0]})
    return {'schema': SCHEMA, 'current': current, 'retired': sorted(retired)}


def current_for(ledger, recipient: dict, claim_kind: str):
    """Current claim for exactly this recipient scope; siblings never inherit it."""
    for row in state(ledger)['current']:
        if row['scope'] == {'recipient': recipient, 'claimKind': claim_kind}:
            return row
    return None
