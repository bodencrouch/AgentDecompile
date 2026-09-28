"""Read-only per-build progress projections for both dashboard surfaces."""
from __future__ import annotations

import time

from .common import corpus_read_snapshot, CorpusReadError
from ..objdiff_report import build_report


_TIERS = ('verified-byte-exact', 'advisory-ghidra', 'unclassified')


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
    groups = {}
    unbound = _new_group(None, 'unbound')
    seen_members = set()
    for unit in report.get('units', ()):
        member_key = unit.get('name')
        if member_key in seen_members:
            raise ValueError(f'duplicate_physical_member:{member_key}')
        seen_members.add(member_key)
        logical_id = unit.get('logical_id')
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
    return {
        'corpus_identity': corpus_identity,
        'binary': {**report['binary'], 'report_sha256': report['report_sha256']},
        'freshness': {'status': 'current'},
        'provider': provider,
        'rows': rows,
        'unbound': _finish_group(unbound),
    }


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


def progress_report(*, slug: str, version: str = '', corpus_identity: str = '') -> dict:
    if not slug:
        return {'ok': True, 'status': 'unselected', 'reason': 'Select a recorded binary to read its progress report'}
    try:
        with corpus_read_snapshot(corpus_identity) as (con, corpus):
            deadline = time.monotonic() + 5
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            row = con.execute('SELECT id,content_sha256 FROM binary WHERE slug=?', (slug,)).fetchone()
            if not row:
                return {'ok': False, 'error': 'Selected binary is not present in this corpus'}
            if version and version != row[1]:
                return {
                    'ok': False,
                    'status': 'stale',
                    'error': 'Requested report version does not match the recorded binary content hash',
                }
            report = build_report(con, row[0], version=row[1])
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
