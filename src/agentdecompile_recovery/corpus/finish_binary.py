"""Reconcile current raw local C observations for one required PE image.

Consumes producer-bound source/target observations in supplied receipt order.
Masked matches remain diagnostic. No compilation, placement, semantic identity
acceptance or linked-image proof is performed by this report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from .verify_recovered_byteexact import file_region_offset

_file_region_offset = file_region_offset


def load_byte_exact(receipts: list[str], *, target_path=None,
                    expected_sizes: dict[int, int] | None = None,
                    rejected: list[dict] | None = None) -> dict[int, str]:
    """Current raw local observations; later supplied rows supersede earlier ones.

    This does not establish semantic identity, toolchain currentness or linked
    contribution. A legacy/masked ``ok`` cannot qualify raw equality.
    """
    from .coverage_evidence import source_binding, target_binding
    from .source_claims import is_real_c
    candidates: dict[tuple[str, int], str] = {}
    target_cache: dict = {}
    def refuse(receipt, row, reason):
        if rejected is not None:
            rejected.append({'receipt': str(receipt), 'file': row.get('file'), 'reason': reason})
    try:
        required_target = Path(target_path).resolve()
        raw = required_target.read_bytes()
        target_cache[('target-binding-v1', str(required_target))] = (raw, hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, TypeError, struct.error):
        refuse(target_path, {}, 'required_pe_target_unavailable')
        return {}
    for r in receipts:
        p = Path(r)
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            refuse(p, {}, 'receipt_unreadable')
            continue
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            refuse(p, {}, 'invalid_receipt')
            continue
        for row in data['results']:
            if not isinstance(row, dict):
                refuse(p, {}, 'invalid_result')
                continue
            source_path = row.get('sourcePath')
            if isinstance(source_path, str) and Path(source_path).is_absolute():
                source_key = str(Path(source_path).resolve())
            else:
                source_key = str(p.resolve()) + ':' + str(row.get('file'))
            try:
                value = row.get('addr')
                addr = value if type(value) is int else int(value, 16) if isinstance(value, str) else -1
            except ValueError:
                addr = -1
            if addr < 0:
                for key in [key for key in candidates if key[0] == source_key]:
                    candidates.pop(key, None)
                refuse(p, row, 'missing_or_invalid_address')
                continue
            candidate_key = (source_key, addr)
            candidates.pop(candidate_key, None)
            if (target_path is None or data.get('current') is False
                    or row.get('ok') is not True or row.get('rawEqual') is not True
                    or row.get('comparisonPolicy') != 'raw-region-v1'):
                refuse(p, row, 'raw_observation_not_qualified')
                continue
            try:
                if not isinstance(source_path, str) or not Path(source_path).is_absolute():
                    raise ValueError('missing absolute source path')
                source = Path(source_path).read_bytes()
                readable = is_real_c(source.decode('utf-8'))
            except (OSError, ValueError):
                refuse(p, row, 'source_unreadable')
                continue
            if not readable or not source_binding(row, source)['current']:
                refuse(p, row, 'source_not_current_readable_c')
                continue
            target = target_binding(row, expected_path=target_path,
                                    expected_address=addr, cache=target_cache)
            if not target['current']:
                refuse(p, row, target['reason'])
                continue
            if _file_region_offset(raw, addr, row['targetRegion']['size']) != row['targetRegion']['offset']:
                refuse(p, row, 'target_address_mapping_mismatch')
                continue
            size = row.get('size')
            if (type(size) is not int or size != row['targetRegion']['size']
                    or expected_sizes is not None and expected_sizes.get(addr) != size):
                refuse(p, row, 'target_function_size_mismatch')
                continue
            candidates[candidate_key] = 'current-source-target-raw-local-observation'
    # Multiple independently current sources may corroborate one address. The
    # report counts that address once only after every source-specific stream
    # has been reconciled.
    return {address: reason for (_, address), reason in candidates.items()}


def contribution_state(observation=None, *, target_path=None, db=None, binary_id=None) -> dict:
    """Explicit opt-in; the default report remains a raw-local observation."""
    from .source_contribution import evaluate_reconstruction
    return evaluate_reconstruction(observation, target_path=target_path, db=db, binary_id=binary_id)


def total_functions(db: str, binary_id: int) -> int:
    import sqlite3
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    n = con.execute("SELECT COUNT(*) FROM func WHERE binary_id=? AND size>0", (binary_id,)).fetchone()[0]
    con.close()
    return n


def text_range(target: bytes) -> tuple[int, int, int]:
    e = struct.unpack_from("<I", target, 0x3C)[0]
    opt = e + 24
    image_base = struct.unpack_from("<I", target, opt + 28)[0]
    nsec = struct.unpack_from("<H", target, e + 6)[0]
    opt_sz = struct.unpack_from("<H", target, e + 20)[0]
    sect = opt + opt_sz
    for i in range(nsec):
        sh = target[sect + i * 40: sect + i * 40 + 40]
        if sh[:8].rstrip(b"\x00").decode("latin1").startswith(".text"):
            vaddr, = struct.unpack_from("<I", sh, 12)
            vsize, = struct.unpack_from("<I", sh, 8)
            return image_base, vaddr, vsize
    raise ValueError("no .text")


def main(*, reconstruction_observation=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipts", nargs="+", required=True,
                    help="verify_recovered_byteexact JSON receipts to union")
    ap.add_argument("--target", required=True, help="shipped exe (whole-image target)")
    ap.add_argument("--db", required=True)
    ap.add_argument("--binary-id", type=int, required=True)
    ap.add_argument("--out", required=True, help="reconciliation report JSON")
    args = ap.parse_args()

    total = total_functions(args.db, args.binary_id)

    import sqlite3
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    funcs = [(int(r[0]), int(r[1] or 0)) for r in con.execute(
        "SELECT addr, size FROM func WHERE binary_id=? AND size>0", (args.binary_id,))]
    con.close()

    rejected: list[dict] = []
    be = load_byte_exact(args.receipts, target_path=args.target,
                         expected_sizes=dict(funcs), rejected=rejected)

    byte_exact = [a for a, _ in funcs if a in be]
    remainder = [a for a, _ in funcs if a not in be]

    contribution = contribution_state(reconstruction_observation, target_path=args.target,
                                      db=args.db, binary_id=args.binary_id)
    report = {
        "target": args.target,
        "totalFunctions": total,
        "byteExactRecoveredC": len(byte_exact),
        "rawLocalObservedC": len(byte_exact),
        "comparisonScope": "current-source-target-raw-local-observation",
        "semanticIdentityVerified": False,
        "linkedSourceContributionVerified": contribution["linkedSourceContributionVerified"],
        "contribution": contribution,
        "placedCompiledRegions": contribution["placedCompiledRegions"],
        "placedCompiledBytes": contribution["placedCompiledBytes"],
        "wholeFileByteIdentical": contribution["wholeFileByteIdentical"],
        "toolchainCurrentnessVerified": False,
        "receiptRejections": rejected,
        "coveragePct": round(100 * len(byte_exact) / max(total, 1), 2),
        "asmFloorRemainder": len(remainder),
        "exactPlacementHashEqual": None,  # No placement or hash comparison is performed here.
        "compilerProducedWholeImage": False,
        "wholeImageByteIdentical": False,
        "claim": ("byteExactRecoveredC is the compatibility count of current-source/target raw local "
                  "observations. Masked comparisons do not qualify. This report does not verify "
                  "semantic identity or a compiler-produced whole image. Optional contribution fields "
                  "independently evaluate a typed reconstruction; absent that input they remain "
                  "unverified. Receipt order defines local-observation supersession."),
        "permuterQueueSample": [f"0x{a:08x}" for a in remainder[:50]],
    }
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f"total functions      : {total}")
    print(f"byte-exact recovered C: {len(byte_exact)}  ({report['coveragePct']}%)")
    print(f"asm-floor remainder   : {len(remainder)}  (permuter work queue)")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
