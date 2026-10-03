"""Exhaustive member accounting and independent byte-extent unions."""
from __future__ import annotations

from collections import Counter

BUCKETS = ('accepted_source', 'candidate_source', 'preserved_region', 'unclassified', 'excluded_with_reason')


def union_bytes(extents):
    ordered = sorted(extents)
    total = 0
    end = None
    for start, stop in ordered:
        if type(start) is not int or type(stop) is not int or start < 0 or stop < start:
            raise ValueError('invalid_byte_extent')
        total += max(0, stop - max(start, end if end is not None else start))
        end = max(end if end is not None else stop, stop)
    return total


def reconcile_inventory(inventory, assignments):
    """Refuse duplicate, missing or foreign members instead of fixing their counts."""
    inventory = list(inventory)
    if len(set(inventory)) != len(inventory):
        raise ValueError('inventory_not_unique')
    counts = Counter()
    members = Counter()
    extents = {bucket: [] for bucket in BUCKETS}
    unknown_extents = []
    for row in assignments:
        member, bucket = row.get('member'), row.get('bucket')
        if bucket not in BUCKETS:
            raise ValueError('unknown_accounting_bucket:' + str(bucket))
        if bucket == 'excluded_with_reason' and not str(row.get('reason') or '').strip():
            raise ValueError('exclusion_reason_missing:' + str(member))
        members[member] += 1
        counts[bucket] += 1
        if row.get('extent') is None:
            unknown_extents.append(member)
        else:
            extent = row['extent']
            if not isinstance(extent, (list, tuple)) or len(extent) != 2:
                raise ValueError('invalid_byte_extent:' + str(member))
            extents[bucket].append(tuple(extent))
    extra = sorted(set(members) - set(inventory))
    missing = sorted(set(inventory) - set(members))
    duplicate = sorted(member for member, count in members.items() if count != 1)
    errors = []
    if extra: errors.append({'code': 'foreign_members', 'members': extra, 'count': len(extra)})
    if missing: errors.append({'code': 'unreconciled_inventory', 'members': missing, 'count': len(missing)})
    if duplicate: errors.append({'code': 'buckets_not_mutually_exclusive', 'members': duplicate, 'count': len(duplicate)})
    return {'status': 'failed' if errors else 'passed', 'inventory_count': len(inventory),
            'buckets': {bucket: counts[bucket] for bucket in BUCKETS}, 'errors': errors,
            'byte_unions': {bucket: union_bytes(extents[bucket]) for bucket in BUCKETS},
            'inventory_byte_union': union_bytes([extent for values in extents.values() for extent in values]),
            'unknown_extent_members': sorted(unknown_extents),
            'byte_accounting': 'incomplete' if unknown_extents else 'complete',
            'note': 'Bucket byte unions may overlap; never add them to infer whole-image coverage.'}
