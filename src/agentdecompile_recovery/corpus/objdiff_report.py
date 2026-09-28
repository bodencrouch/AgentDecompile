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


def build_report(con, binary_id: int, *, version: str, receipts=(), verify_receipt=None):
    if not isinstance(version, str) or not version.strip():
        raise ValueError('report_version_required')
    columns = {row[1] for row in con.execute('PRAGMA table_info(binary)')}
    if 'content_sha256' not in columns:
        raise ValueError('binary_content_identity_required')
    row = con.execute('SELECT slug,content_sha256 FROM binary WHERE id=?', (binary_id,)).fetchone()
    if not row:
        raise ValueError('binary_not_found')
    slug, target_hash = row
    if not isinstance(target_hash, str) or len(target_hash) != 64 or any(c not in '0123456789abcdef' for c in target_hash):
        raise ValueError('binary_content_identity_required')
    functions = con.execute('SELECT addr,name,size,ranges FROM func WHERE binary_id=? ORDER BY addr', (binary_id,)).fetchall()
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    sources = {}
    if 'recovered_function' in tables:
        fields = {r[1] for r in con.execute('PRAGMA table_info(recovered_function)')}
        if {'binary_id','addr','source_sha256','target_sha256','real_c'} <= fields:
            for addr, source_hash in con.execute('SELECT addr,source_sha256 FROM recovered_function WHERE binary_id=? AND target_sha256=? AND real_c=1 ORDER BY addr,source_sha256', (binary_id,target_hash)):
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
    unknown_sizes = []
    for addr,name,size,ranges in functions:
        member = f'{target_hash}:{addr:x}'
        known = type(size) is int and size >= 0
        if not known: unknown_sizes.append(member)
        extent = [addr,addr+size] if known and ranges == 1 else None
        tier = 'verified-byte-exact' if addr in qualified else 'advisory-ghidra' if addr in sources else 'unclassified'
        bucket = 'accepted_source' if tier=='verified-byte-exact' else 'candidate_source' if tier=='advisory-ghidra' else 'unclassified'
        tier_counts[tier] += 1
        tier_bytes[tier] += size if known else 0
        pct = 100 if tier=='verified-byte-exact' else 0
        unit = {'name':member,'display_name':name,'address':hex(addr),'tier':tier,
                'measures':{'total_code':size if known else None,'matched_code':size if known and pct else 0,
                            'matched_percent':pct,'total_functions':1,'matched_functions':int(bool(pct))},
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
