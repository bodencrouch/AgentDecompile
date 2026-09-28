"""Qualify a narrow PE32 raw-byte substrate extent, never source equivalence.

Cached size is a body-byte count. Cached addressed instructions propose bounds;
current image bytes and a closed, independently decoded direct CFG qualify them.
Calls are opaque and assumed to return. Relocation/link correctness remains open.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import re
import shutil
import os
import selectors
import time
import subprocess
import tempfile

from .source_contribution import pe_region

MAX_SPAN = 4096
LINE = re.compile(r'^\s*([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2}\s+)+)(.*)$')
ORDINARY = frozenset('mov movzx movsx push pop lea test cmp dec inc sub add xor and or shl shr sar mul imul neg not nop nopl nopw seto'.split())


@lru_cache(maxsize=1)
def image_digest(raw: bytes):
    """One immutable loaded image; avoid rehashing a corpus image per function."""
    return hashlib.sha256(raw).hexdigest()


def listing(text):
    if not isinstance(text, str) or len(text) > 256 * 1024:
        raise ValueError('instruction_listing_unavailable_or_unbounded')
    rows = {}
    for line in (text or '').splitlines():
        match = LINE.match(line)
        if not match: continue
        address = int(match[1], 16)
        if address in rows: raise ValueError('duplicate_instruction_address')
        raw = bytes.fromhex(match[2])
        if not 1 <= len(raw) <= 15: raise ValueError('invalid_instruction_length')
        rows[address] = (raw, match[3].strip())
    if not rows: raise ValueError('instruction_coverage_unavailable')
    return rows


def decoder_identity():
    decoder = shutil.which('objdump')
    if not decoder: raise ValueError('extent_decoder_unavailable')
    decoder = Path(decoder).resolve(strict=True)
    return {'path': str(decoder), 'sha256': hashlib.sha256(decoder.read_bytes()).hexdigest()}


def decode(blob, address):
    identity = decoder_identity()
    with tempfile.TemporaryDirectory(prefix='agentdecompile-extent-') as directory:
        path = Path(directory) / 'span.bin'
        path.write_bytes(blob)
        proc = subprocess.Popen([identity['path'], '-D', '-b', 'binary', '-m', 'i386',
                                 '--insn-width=16', '--adjust-vma=' + str(address), str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        output = bytearray(); deadline = time.monotonic() + 5
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    if time.monotonic() >= deadline: raise ValueError('extent_decoder_timeout')
                    if not selector.select(.05): continue
                    chunk = os.read(proc.stdout.fileno(), 4096)
                    if not chunk: break
                    output.extend(chunk)
                    if len(output) > 256 * 1024: raise ValueError('extent_decoder_output_limit')
            if proc.wait(timeout=max(.01, deadline-time.monotonic())) != 0:
                raise ValueError('extent_decoder_failed')
        finally:
            if proc.poll() is None: proc.kill()
            proc.wait(); proc.stdout.close()
    if decoder_identity() != identity: raise ValueError('extent_decoder_changed')
    return listing(output.decode('ascii', errors='strict')), identity


def qualify(raw, address, file_offset, body_count, assembly, image_sha256):
    if not re.fullmatch(r'[0-9a-f]{64}', str(image_sha256 or '')):
        raise ValueError('original_image_identity_unavailable')
    if image_digest(raw) != image_sha256:
        raise ValueError('original_image_identity_mismatch')
    cached = listing(assembly)
    end = max(at + len(item[0]) for at, item in cached.items())
    size = end - address
    if min(cached) != address or not 0 < size <= MAX_SPAN:
        raise ValueError('unsupported_candidate_extent')
    region = pe_region(raw, address, size)
    if region['machine'] != 0x14c: raise ValueError('extent_requires_pe32_x86')
    if region['offset'] != file_offset: raise ValueError('cache_file_offset_mismatch')
    blob = raw[file_offset:file_offset + size]
    covered = set()
    for at, (encoded, _) in cached.items():
        offset = at - address
        positions = set(range(offset, offset + len(encoded)))
        if positions & covered: raise ValueError('overlapping_cached_instructions')
        if blob[offset:offset + len(encoded)] != encoded: raise ValueError('cached_bytes_differ')
        covered.update(positions)
    if type(body_count) is not int or body_count != len(covered):
        raise ValueError('unsupported_cache_body_count')
    decoded, decoder = decode(blob, address)
    cursor = address
    for at, (encoded, text) in sorted(decoded.items()):
        if at != cursor or blob[at-address:at-address+len(encoded)] != encoded:
            raise ValueError('decoder_coverage_mismatch')
        if not text or '(bad)' in text or text.startswith('.'):
            raise ValueError('undecodable_original_bytes')
        cursor += len(encoded)
    if cursor != end: raise ValueError('incomplete_original_decode')
    for at, (encoded, _) in cached.items():
        if at not in decoded or decoded[at][0] != encoded:
            raise ValueError('cache_instruction_boundary_mismatch')
    pending = [address]; reachable = set(); returns = set(); edges = {}
    while pending:
        at = pending.pop()
        if at in reachable: continue
        if at not in decoded: raise ValueError('control_flow_outside_extent_or_mid_instruction')
        reachable.add(at)
        encoded, text = decoded[at]; mnemonic = text.split()[0]
        following = at + len(encoded)
        if encoded == b'\xc3' or (len(encoded) == 3 and encoded[0] == 0xc2):
            returns.add(at); continue
        if encoded[0] == 0xe8 and len(encoded) == 5:
            successors = [following]  # Opaque callee, not semantic acceptance.
        elif encoded[0] in (0xeb, 0xe9):
            width = 1 if encoded[0] == 0xeb else 4
            if len(encoded) != width + 1: raise ValueError('unsupported_branch_encoding')
            successors = [following + int.from_bytes(encoded[1:], 'little', signed=True)]
        elif len(encoded) == 2 and 0x70 <= encoded[0] <= 0x7f:
            successors = [following, following + int.from_bytes(encoded[1:], 'little', signed=True)]
        elif len(encoded) == 6 and encoded[0] == 0x0f and 0x80 <= encoded[1] <= 0x8f:
            successors = [following, following + int.from_bytes(encoded[2:], 'little', signed=True)]
        elif mnemonic in ORDINARY:
            successors = [following]
        else:
            raise ValueError('unsupported_extent_instruction:' + mnemonic)
        edges[at] = successors
        pending.extend(successors)
    if not returns or max(at + len(decoded[at][0]) for at in reachable) != end:
        raise ValueError('extent_has_no_reachable_terminal_boundary')
    can_return = set(returns)
    while True:
        expanded = can_return | {at for at, targets in edges.items() if any(t in can_return for t in targets)}
        if expanded == can_return: break
        can_return = expanded
    if reachable - can_return: raise ValueError('closed_control_flow_without_return_path')
    for at, (_, text) in decoded.items():
        if at not in reachable and not (text.split()[0] in {'nop', 'nopl', 'nopw'}
                or re.fullmatch(r'lea\s+0x0\(%(e[a-z]+)\),%\1', text)):
            raise ValueError('unsupported_unreachable_gap')
    return {'offset': file_offset, 'size': size, 'bodyBytes': body_count,
            'coveredBytes': len(covered), 'uncoveredOffsets': sorted(set(range(size)) - covered),
            'imageSha256': image_sha256, 'spanSha256': hashlib.sha256(blob).hexdigest(),
            'decoder': decoder, 'claim': 'bounded-direct-cfg-original-byte-substrate-only'}
