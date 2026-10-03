"""Corpus inventory -> objdiff-shaped progress; no compilation or publication.

Stored recovered source is advisory. Promotion requires an input-bound acceptance
receipt and an independent verifier supplied by the acceptance owner. This report
never treats a source classification, donor match or copied byte string as proof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .report_accounting import reconcile_inventory

FORMAT = 'agentdecompile.objdiff-progress/v1'
MAX_LOGICAL_ID = 9007199254740991


def validate_logical_id(logical_id: int | None) -> None:
    if logical_id is not None and (type(logical_id) is not int
                                   or not 0 < logical_id <= MAX_LOGICAL_ID):
        raise ValueError('logical_id_invalid')


def _selected_inventory(con, binary_id: int, logical_id: int):
    """Read only selected members, but inspect every claim at their addresses."""
    schemas = {name: (kind, sql) for name, kind, sql in con.execute(
        "SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view')")}
    required = {
        'binary': {'id', 'slug', 'content_sha256'},
        'func': {'binary_id', 'addr', 'name', 'size', 'ranges'},
        'identity': {'logical_id', 'binary_id', 'addr'},
        'logical_function': {'id', 'canon_key'},
    }
    source_fields = {'binary_id', 'addr', 'source_sha256', 'target_sha256', 'real_c'}
    if 'recovered_function' in schemas:
        required['recovered_function'] = source_fields
    for table, consumed in required.items():
        kind, sql = schemas.get(table, (None, None))
        if kind != 'table' or not sql or 'CREATE VIRTUAL TABLE' in sql.upper():
            raise ValueError('selected_report_table_required:' + table)
        if not consumed <= {row[1] for row in con.execute('PRAGMA table_info(' + table + ')')}:
            raise ValueError('selected_report_schema_invalid:' + table)
    roots = con.execute('SELECT id,canon_key FROM logical_function WHERE id=?',
                        (logical_id,)).fetchall()
    if not roots:
        raise ValueError('logical_function_not_found')
    if len(roots) != 1 or type(roots[0][0]) is not int or roots[0][0] != logical_id:
        raise ValueError('logical_function_root_ambiguous')
    canon_key = roots[0][1]
    if canon_key is not None and not isinstance(canon_key, str):
        raise ValueError('logical_function_root_malformed')
    stable_key = canon_key or f'logical:{logical_id}'
    binary_rows = con.execute('SELECT id,slug,content_sha256 FROM binary WHERE id=?',
                             (binary_id,)).fetchall()
    if (len(binary_rows) != 1 or type(binary_rows[0][0]) is not int
            or binary_rows[0][0] != binary_id or not isinstance(binary_rows[0][1], str)
            or not binary_rows[0][1]):
        raise ValueError('selected_binary_ambiguous_or_malformed')
    selected = con.execute(
        'SELECT logical_id,binary_id,addr FROM identity WHERE logical_id=? AND binary_id=?',
        (logical_id, binary_id)).fetchall()
    addresses = set()
    for root_id, build_id, addr in selected:
        if (type(root_id) is not int or root_id != logical_id
                or type(build_id) is not int or build_id != binary_id
                or type(addr) is not int or addr < 0 or addr in addresses):
            raise ValueError('selected_membership_malformed_or_duplicate')
        addresses.add(addr)
    # EXISTS keeps each physical function once; malformed duplicate func rows
    # are refused below instead of being hidden by DISTINCT or a joined fan-out.
    membership = ('SELECT 1 FROM identity s WHERE s.logical_id=? AND s.binary_id=? '
                  'AND s.addr=f.addr')
    functions = con.execute(
        'SELECT f.addr,f.name,f.size,f.ranges FROM func f WHERE f.binary_id=? '
        'AND EXISTS (' + membership + ') ORDER BY f.addr',
        (binary_id, logical_id, binary_id)).fetchall()
    function_addresses = [row[0] for row in functions]
    if (any(type(addr) is not int or addr < 0 for addr in function_addresses)
            or len(set(function_addresses)) != len(function_addresses)
            or set(function_addresses) != addresses):
        raise ValueError('selected_membership_function_mismatch')
    claims = con.execute(
        'SELECT i.logical_id,i.binary_id,i.addr FROM identity i WHERE i.binary_id=? '
        'AND EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=? AND s.binary_id=? '
        'AND s.addr=i.addr) ORDER BY i.addr',
        (binary_id, logical_id, binary_id)).fetchall()
    claimed = set()
    for root_id, build_id, addr in claims:
        if (type(root_id) is not int or root_id != logical_id
                or type(build_id) is not int or build_id != binary_id
                or type(addr) is not int or addr not in addresses or addr in claimed):
            raise ValueError('selected_identity_conflicting_or_duplicate')
        claimed.add(addr)
    if claimed != addresses:
        raise ValueError('selected_identity_membership_mismatch')
    identities = {addr: {'logical_id': logical_id, 'stable_key': stable_key}
                  for addr in addresses}
    return functions, identities, stable_key


def build_report(con, binary_id: int, *, version: str, receipts=(), verify_receipt=None,
                 logical_id: int | None = None):
    validate_logical_id(logical_id)
    if not isinstance(version, str) or not version.strip():
        raise ValueError('report_version_required')
    selected_inventory = (_selected_inventory(con, binary_id, logical_id)
                          if logical_id is not None else None)
    columns = {row[1] for row in con.execute('PRAGMA table_info(binary)')}
    if 'content_sha256' not in columns:
        raise ValueError('binary_content_identity_required')
    row = con.execute('SELECT slug,content_sha256 FROM binary WHERE id=?', (binary_id,)).fetchone()
    if not row:
        raise ValueError('binary_not_found')
    slug, target_hash = row
    if not isinstance(target_hash, str) or len(target_hash) != 64 or any(c not in '0123456789abcdef' for c in target_hash):
        raise ValueError('binary_content_identity_required')
    if logical_id is not None and version != target_hash:
        raise ValueError('selected_report_version_mismatch')
    functions = (selected_inventory[0] if selected_inventory is not None else
                 con.execute('SELECT addr,name,size,ranges FROM func WHERE binary_id=? ORDER BY addr', (binary_id,)).fetchall())
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    identities = selected_inventory[1] if selected_inventory is not None else {}
    if selected_inventory is None and 'identity' in tables:
        identity_fields = {r[1] for r in con.execute('PRAGMA table_info(identity)')}
        if {'logical_id', 'binary_id', 'addr'} <= identity_fields:
            identity_rows = ((root_id, addr, None) for root_id, addr in con.execute(
                'SELECT logical_id,addr FROM identity WHERE binary_id=? ORDER BY addr',
                (binary_id,)))
            if 'logical_function' in tables:
                logical_fields = {r[1] for r in con.execute('PRAGMA table_info(logical_function)')}
                if {'id', 'canon_key'} <= logical_fields:
                    identity_rows = con.execute(
                        'SELECT i.logical_id,i.addr,l.canon_key '
                        'FROM identity i LEFT JOIN logical_function l ON l.id=i.logical_id '
                        'WHERE i.binary_id=? ORDER BY i.addr',
                        (binary_id,))
            for root_id, addr, canon_key in identity_rows:
                identities[addr] = {
                    'logical_id': root_id,
                    'stable_key': canon_key or f'logical:{root_id}',
                }
    sources = {}
    if 'recovered_function' in tables:
        fields = {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')}
        if {'binary_id','addr','source_sha256','target_sha256','real_c'} <= fields:
            source_sql = ('SELECT r.addr,r.source_sha256 FROM recovered_function r '
                          'WHERE r.binary_id=? AND r.target_sha256=? AND r.real_c=1')
            source_args = (binary_id, target_hash)
            if logical_id is not None:
                source_sql += (' AND EXISTS (SELECT 1 FROM identity s WHERE s.logical_id=? '
                               'AND s.binary_id=? AND s.addr=r.addr)')
                source_args += (logical_id, binary_id)
            source_sql += ' ORDER BY r.addr,r.source_sha256'
            for addr, source_hash in con.execute(source_sql, source_args):
                if isinstance(source_hash,str) and len(source_hash)==64 and all(c in '0123456789abcdef' for c in source_hash):
                    sources.setdefault(addr,set()).add(source_hash)
    qualified = {}
    refused = []
    for receipt in receipts:
        if not isinstance(receipt,dict):
            raise ValueError('acceptance_receipt_not_object')
        addr = receipt.get('addr')
        eligible = (receipt.get('target_sha256') == target_hash
                    and receipt.get('source_sha256') in sources.get(addr,set())
                    and receipt.get('version') == version
                    and receipt.get('status') == 'accepted'
                    and receipt.get('claim') == 'byte_exact_source'
                    and callable(verify_receipt))
        if eligible and verify_receipt(receipt) is True:
            if addr in qualified:
                raise ValueError('ambiguous_acceptance_receipts:' + str(addr))
            qualified[addr] = receipt
        else:
            refused.append({'addr':addr,'reason':'independent_input_bound_acceptance_not_established'})
    units, assignments = [], []
    tier_counts = {'verified-byte-exact':0,'advisory-ghidra':0,'unclassified':0}
    tier_bytes = dict.fromkeys(tier_counts,0)
    unknown_tier_extents = set()
    unknown_sizes = []
    for addr,name,size,ranges in functions:
        member = f'{target_hash}:{addr:x}'
        known = type(size) is int and size >= 0
        if not known or (logical_id is not None and ranges != 1): unknown_sizes.append(member)
        extent = [addr,addr+size] if known and ranges == 1 else None
        tier = 'verified-byte-exact' if addr in qualified else 'advisory-ghidra' if addr in sources else 'unclassified'
        if extent is None:
            unknown_tier_extents.add(tier)
        bucket = 'accepted_source' if tier=='verified-byte-exact' else 'candidate_source' if tier=='advisory-ghidra' else 'unclassified'
        tier_counts[tier] += 1
        tier_bytes[tier] += size if known else 0
        pct = 100 if tier=='verified-byte-exact' else 0
        scoped_unknown_extent = logical_id is not None and extent is None
        unit = {'name':member,'display_name':name,'address':hex(addr),'tier':tier,
                'logical_id':identities.get(addr, {}).get('logical_id'),
                'stable_key':identities.get(addr, {}).get('stable_key'),
                'extent_known':known and ranges == 1,
                'measures':{'total_code':size if known and not scoped_unknown_extent else None,
                            'matched_code':None if scoped_unknown_extent and pct else size if known and pct else 0,
                            'matched_percent':None if scoped_unknown_extent else pct,
                            'total_functions':1,'matched_functions':int(bool(pct))},
                'functions':[{'name':name,'size':size if known else None,'fuzzy_match_percent':pct}]}
        if addr in qualified:
            unit['acceptance_receipt_sha256'] = hashlib.sha256(_bytes(qualified[addr])).hexdigest()
        units.append(unit)
        assignments.append({'member':member,'bucket':bucket,'extent':extent})
    inventory = [unit['name'] for unit in units]
    accounting = reconcile_inventory(inventory,assignments)
    total = sum(tier_bytes.values())
    percent = None if unknown_sizes or not total else 100*tier_bytes['verified-byte-exact']/total
    report = {'format':FORMAT,'binary':{'id':binary_id,'slug':slug,'content_sha256':target_hash,'version':version},
              'units':units,'measures':{'total_code':None if unknown_sizes else total,'matched_code':tier_bytes['verified-byte-exact'],
                  'matched_percent':percent,'total_functions':len(units),'matched_functions':tier_counts['verified-byte-exact']},
              'tiers':{tier:{'functions':tier_counts[tier],'bytes':tier_bytes[tier]} for tier in tier_counts},
              'accounting':accounting,'assignments':assignments,'unqualified_receipts':refused,
              'tier_note':'Advisory is recorded unverified source; the legacy tier label does not independently establish Ghidra provenance.',
              'verification':'reused_acceptance_receipts_only','fresh_compilation':'not_run','published':False}
    if logical_id is not None:
        report['selection_scope'] = {'kind': 'logical_function', 'logical_id': logical_id}
        report['selection_root'] = {'logical_id': logical_id, 'stable_key': selected_inventory[2]}
        for tier in unknown_tier_extents:
            report['tiers'][tier]['bytes'] = None
        if 'verified-byte-exact' in unknown_tier_extents:
            report['measures']['matched_code'] = None
    report['report_sha256'] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def _bytes(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def export_report(con, binary_id: int, out: Path | str, *, version: str, receipts=(), verify_receipt=None):
    report=build_report(con,binary_id,version=version,receipts=receipts,verify_receipt=verify_receipt)
    if report['accounting']['status']!='passed':
        raise ValueError('report_inventory_unreconciled')
    target=Path(out)
    target.parent.mkdir(parents=True,exist_ok=True)
    # Artifact generation has no outbound publication side effect.
    target.write_bytes(_bytes(report))
    return {'wrote':str(target),'report_sha256':report['report_sha256'],'published':False}
