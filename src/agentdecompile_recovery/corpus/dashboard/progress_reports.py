"""Read-only per-build progress projections for both dashboard surfaces."""
from __future__ import annotations

import re
import time

from .common import corpus_read_snapshot, CorpusReadError
from ..objdiff_report import build_report, validate_logical_id, MAX_LOGICAL_ID


_TIERS = ('verified-byte-exact', 'advisory-ghidra', 'unclassified')


def parse_logical_id(values: list[str]) -> int | None:
    """An absent query is unfiltered; every present value must be canonical."""
    if not values:
        return None
    if len(values) != 1 or not re.fullmatch(r'[1-9][0-9]{0,15}', values[0]):
        raise ValueError('logical_id_invalid')
    logical_id = int(values[0])
    if logical_id > MAX_LOGICAL_ID:
        raise ValueError('logical_id_invalid')
    return logical_id


def logical_tier_projection(report: dict, *, corpus_identity: str) -> dict:
    """Roll one physical report up by logical identity without reclassifying it."""
    accounting = report.get('accounting', {})
    if accounting.get('status') != 'passed':
        raise ValueError('objdiff_report_accounting_failed')
    provider = {
        'status': 'not_connected',
        'reason': ('No independent byte-acceptance provider is connected to this '
                   'projection; source classifications remain advisory'),
    }
    scope = report.get('selection_scope')
    selected_id = None
    groups = {}
    if 'selection_scope' in report:
        if not isinstance(scope, dict) or set(scope) != {'kind', 'logical_id'} or scope.get('kind') != 'logical_function':
            raise ValueError('logical_selection_scope_invalid')
        selected_id = scope.get('logical_id')
        validate_logical_id(selected_id)
        root = report.get('selection_root', {})
        if (not isinstance(root, dict) or selected_id is None or type(root.get('logical_id')) is not int
                or root.get('logical_id') != selected_id
                or not isinstance(root.get('stable_key'), str) or not root['stable_key']):
            raise ValueError('logical_selection_root_invalid')
        groups[selected_id] = _new_group(selected_id, root['stable_key'])
    unbound = _new_group(None, 'unbound')
    seen_members = set()
    for unit in report.get('units', ()):
        member_key = unit.get('name')
        if member_key in seen_members:
            raise ValueError(f'duplicate_physical_member:{member_key}')
        seen_members.add(member_key)
        logical_id = unit.get('logical_id')
        if selected_id is not None and (type(logical_id) is not int or logical_id != selected_id
                                       or unit.get('stable_key') != groups[selected_id]['stable_key']):
            raise ValueError('logical_selection_membership_mismatch')
        if logical_id is None:
            group = unbound
        else:
            if logical_id not in groups:
                groups[logical_id] = _new_group(
                    logical_id, unit.get('stable_key') or f'logical:{logical_id}')
            group = groups[logical_id]
        _add_unit(group, unit)

    if accounting.get('inventory_count') != len(seen_members):
        raise ValueError('objdiff_report_inventory_mismatch')

    rows = [_finish_group(groups[logical_id])
            for logical_id in sorted(groups)]
    projection = {
        'corpus_identity': corpus_identity,
        'binary': {**report['binary'], 'report_sha256': report['report_sha256']},
        'freshness': {'status': 'current'},
        'provider': provider,
        'rows': rows,
        'unbound': _finish_group(unbound),
    }
    if selected_id is not None:
        projection.update(selection_scope=dict(scope), unbound=None, unbound_status='not_requested')
    return projection


def _new_group(logical_id, stable_key: str) -> dict:
    return {
        'logical_id': logical_id,
        'stable_key': stable_key,
        'physical_members': 0,
        'member_keys': [],
        'tiers': {tier: {'member_keys': [], 'bytes': 0, 'unknown': False}
                  for tier in _TIERS},
        'unknown_extent_members': 0,
    }


def _add_unit(group: dict, unit: dict) -> None:
    tier = unit.get('tier')
    if tier not in _TIERS:
        raise ValueError(f'unknown_objdiff_tier:{tier}')
    member_key = unit.get('name')
    if not isinstance(member_key, str) or not member_key:
        raise ValueError('physical_member_key_required')
    group['physical_members'] += 1
    group['member_keys'].append(member_key)
    bucket = group['tiers'][tier]
    bucket['member_keys'].append(member_key)
    size = unit.get('measures', {}).get('total_code')
    if unit.get('extent_known') is True and type(size) is int and size >= 0:
        bucket['bytes'] += size
    else:
        bucket['unknown'] = True
        group['unknown_extent_members'] += 1


def _finish_group(group: dict) -> dict:
    def tier_counts(tier: str) -> dict:
        bucket = group['tiers'][tier]
        return {
            'functions': len(bucket['member_keys']),
            'bytes': None if bucket['unknown'] else bucket['bytes'],
            'member_keys': list(bucket['member_keys']),
        }

    verified = tier_counts('verified-byte-exact')
    verified['status'] = 'unavailable'
    verified['functions'] = None
    verified['bytes'] = None
    return {
        'logical_id': group['logical_id'],
        'stable_key': group['stable_key'],
        'physical_members': group['physical_members'],
        'member_keys': list(group['member_keys']),
        'verified': verified,
        'advisory': tier_counts('advisory-ghidra'),
        'unclassified': tier_counts('unclassified'),
        'unknown_extent_members': group['unknown_extent_members'],
    }


def progress_report(*, slug: str, version: str = '', corpus_identity: str = '',
                    logical_id: int | None = None) -> dict:
    try:
        validate_logical_id(logical_id)
        if not slug:
            if logical_id is not None:
                raise ValueError('selected_binary_required')
            return {'ok': True, 'status': 'unselected', 'reason': 'Select a recorded binary to read its progress report'}
        if logical_id is not None and (not corpus_identity or not version):
            raise ValueError('selected_corpus_and_version_required')
        with corpus_read_snapshot(corpus_identity) as (con, corpus):
            deadline = time.monotonic() + 5
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            rows = con.execute('SELECT id,content_sha256 FROM binary WHERE slug=?', (slug,)).fetchall()
            if logical_id is not None and len(rows) > 1:
                raise ValueError('selected_binary_ambiguous')
            row = rows[0] if rows else None
            if not row:
                payload = {'ok': False, 'error': 'Selected binary is not present in this corpus'}
                if logical_id is not None:
                    payload['status'] = 'unavailable'
                return payload
            if version and version != row[1]:
                return {
                    'ok': False,
                    'status': 'stale',
                    'error': 'Requested report version does not match the recorded binary content hash',
                }
            report = build_report(con, row[0], version=row[1], logical_id=logical_id)
            matrix_projection = logical_tier_projection(
                report, corpus_identity=corpus['identity'])
            return {'ok': True, 'status': 'available', 'corpus': corpus,
                    'report': {key:value for key,value in report.items() if key not in ('units','assignments')},
                    'matrix_projection': matrix_projection,
                    'acceptance_provider': {
                        'status': 'unavailable',
                        'reason': matrix_projection['provider']['reason'],
                    }}
    except (CorpusReadError, ValueError) as exc:
        return {'ok': False, 'status': 'unavailable', 'error': str(exc)}
