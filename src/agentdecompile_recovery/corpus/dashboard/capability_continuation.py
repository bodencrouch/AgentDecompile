"""Signed, input-bound protection capability changes in preparation state.

Publication is a controller operation: ``preparation.publish_capability(envelope)``.
The producer and an independent configured operator/fleet reviewer sign
``attestation_bytes(claim, role)``. No keys, roles or lineage are enrolled here.
The reviewer attests the retained qualification evidence under POLICY; publication
checks that evidence, signatures and current artifacts before saving a wake.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

POLICY = 'agentdecompile.protection-capability-acceptance.v1'
_HEX = re.compile(r'^[0-9a-f]{64}$')


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest_file(path: str | Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def attestation_bytes(claim: dict, role: str) -> bytes:
    if role not in {'producer', 'reviewer'}:
        raise ValueError('Unknown capability attestation role')
    return encoded({'domain': POLICY, 'role': role, 'claim': claim})


def event_id(envelope: dict) -> str:
    # Re-signing the same claim is not a new capability or admission.
    return hashlib.sha256(encoded(envelope['claim'])).hexdigest()


def _authority():
    from agentdecompile_grid.config import GridConfig
    from agentdecompile_grid.log.signing import Keyring
    from agentdecompile_grid.objects.local import LocalDirStore
    from agentdecompile_grid.verify.policy import RevocationList
    config = GridConfig.load()
    if config.adapters.objects != 'local':
        raise ValueError('Capability acceptance requires the configured local grid revocation store')
    ring = Keyring.from_locator(config.keyring_locator())
    # Missing/corrupt established policy state is not a fresh empty authority.
    store = LocalDirStore.from_config(config, create=False)
    if store.get_named('policy/revoked') is None:
        raise ValueError('Capability acceptance requires an explicit grid revocation ledger')
    return ring, RevocationList.load(store)


def verify(envelope: dict) -> dict:
    """Revalidate configured trust and immutable evidence on every consumption."""
    from .protection import capability_manifest
    if not isinstance(envelope, dict) or not isinstance(envelope.get('claim'), dict):
        raise ValueError('Missing capability claim')
    claim = envelope['claim']
    if claim.get('policy') != POLICY or claim.get('outcome') != 'accepted':
        raise ValueError('Capability policy or acceptance outcome is unsupported')
    if claim.get('capability') != 'protection:UPX':
        raise ValueError('Unsupported protection capability')
    if not isinstance(claim.get('preparationId'), str) or not re.fullmatch(r'[0-9a-f]{32}', claim['preparationId']):
        raise ValueError('Invalid preparation identity')
    if not isinstance(claim.get('program'), str) or not claim['program']:
        raise ValueError('Missing exact program identity')
    for key in ('inputSha256', 'revision'):
        if not isinstance(claim.get(key), str) or not _HEX.fullmatch(claim[key]):
            raise ValueError('Invalid capability ' + key)
    expires = claim.get('expiresAt')
    if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= time.time():
        raise ValueError('Capability acceptance expired or has no expiry')
    from agentdecompile_grid.core import GridError
    try:
        ring, revoked = _authority()
    except GridError as exc:
        raise ValueError('Configured capability authority is unavailable: ' + str(exc)) from exc
    signers = []
    for role in ('producer', 'reviewer'):
        attestation = envelope.get(role) or {}
        key = attestation.get('key', '')
        # Null/HMAC/hash-token development identities do not establish two
        # separately controlled acceptance authorities for this policy.
        if not isinstance(key, str) or not key.startswith('ed25519:'):
            raise ValueError('Capability acceptance requires configured Ed25519 identities')
        if revoked.is_revoked(key) or not ring.knows(key):
            raise ValueError('Capability signer is unknown or revoked')
        if role == 'reviewer' and ring.role_of(key) not in {'operator', 'fleet'}:
            raise ValueError('Capability reviewer lacks configured acceptance role')
        if not ring.verify(key, attestation_bytes(claim, role), attestation.get('signature', '')):
            raise ValueError('Capability attestation signature is invalid')
        signers.append(key)
    if not ring.independent(*signers):
        raise ValueError('Capability producer and reviewer are not independent')
    manifest = capability_manifest('UPX')
    if not manifest.get('available') or claim.get('artifacts') != manifest['artifacts'] or claim['revision'] != manifest['revision']:
        raise ValueError('Accepted capability artifacts are unavailable or changed')
    evidence = claim.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('Capability qualification evidence is missing')
    for item in evidence:
        if not isinstance(item, dict) or not _HEX.fullmatch(str(item.get('sha256', ''))):
            raise ValueError('Invalid qualification evidence reference')
        if digest_file(item['path']) != item['sha256']:
            raise ValueError('Qualification evidence changed')
    return claim


def publish(directory: Path, envelope: dict) -> str:
    verify(envelope)
    key = event_id(envelope)
    target = directory / 'capabilities'
    target.mkdir(exist_ok=True)
    final = target / (key + '.json')
    if final.exists():
        verify(json.loads(final.read_text()))
        return key
    temporary = target / (key + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(encoded(envelope))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(final)
    fd = os.open(target, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return key


def read_event(directory: Path, key: str) -> dict:
    if not _HEX.fullmatch(str(key)):
        raise ValueError('Invalid capability event identity')
    envelope = json.loads((directory / 'capabilities' / (key + '.json')).read_text())
    if event_id(envelope) != key:
        raise ValueError('Capability event content identity changed')
    return envelope


def blocked_requirement(row: dict, program: str, observation: dict) -> dict:
    from .protection import capability_manifest
    protector = (observation.get('detection') or {}).get('protector')
    capability = 'protection:' + str(protector or 'unknown')
    manifest = capability_manifest(str(protector))
    return {'capability': capability, 'preparationId': row['id'], 'program': program,
            'inputSha256': observation.get('sourceSha256'),
            'observedRevision': observation.get('capabilityRevision') or manifest['revision'],
            'state': 'waiting', 'reason': 'An independently accepted changed capability is required.',
            'nextAction': 'await_accepted_capability', 'policy': POLICY}


def check_wait(row: dict, program: str, claim: dict) -> None:
    checkpoint = (row.get('checkpoints') or {}).get(program) or {}
    wait = checkpoint.get('blockedRequirement') or {}
    if (claim['preparationId'] != row['id'] or claim['program'] != program
            or wait.get('capability') != claim['capability']
            or wait.get('inputSha256') != claim['inputSha256']):
        raise ValueError('Capability claim does not match this blocked dependency')
    if wait.get('observedRevision') == claim['revision']:
        raise ValueError('Capability basis is unchanged; no automatic retry')
    if digest_file(checkpoint.get('executablePath') or '') != claim['inputSha256']:
        raise ValueError('Blocked input bytes changed; reconcile input identity')


def admission_refusal(row: dict, command: dict, *, owner_busy: bool) -> str:
    if row.get('supersededBy'):
        return 'Preparation has been superseded'
    if command.get('operation') in {'pause', 'stop'} or row.get('status') in {'paused', 'cancelled'}:
        return 'Preparation is paused or stopped'
    if owner_busy:
        return 'An existing preparation owner must finish or be reconciled'
    deadline = command.get('deadline', row.get('deadline'))
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= time.time()):
        return 'Preparation deadline expired or is invalid'
    for prior in (row.get('actions') or {}).values():
        if not isinstance(prior, dict):
            return 'Action ownership/accounting requires reconciliation'
        result = prior.get('result') or {}
        if (prior.get('status') in {'submitting', 'queued', 'running', 'interrupted', 'cancelling'}
                or result.get('ownershipUnresolved') or result.get('unknownOutcome')
                or result.get('ownershipResolved') is False):
            return 'An earlier action has unresolved ownership or effects'
    from . import admission_budget, mcp_budget
    try:
        budget = admission_budget.initialize(row)
        if budget['priorUsageUnknown']:
            return 'Prior objective spending is unknown'
        if budget['maxActionAdmissions'] is not None and budget['consumed'] >= budget['maxActionAdmissions']:
            return 'Objective admission budget is exhausted'
        provider = mcp_budget.initialize(row)
        if provider['priorUsageUnknown']:
            return 'Prior provider spending is unknown'
        if mcp_budget.exhausted(row):
            return 'Provider dispatch budget is exhausted'
    except ValueError as exc:
        return str(exc)
    return ''
