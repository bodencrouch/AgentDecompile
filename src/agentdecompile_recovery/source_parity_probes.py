"""Original-executable bound source hypotheses; compilation remains the gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from bisect import bisect_left
from pathlib import Path
from typing import Any

from .corpus.exact_corpus import coff_functions
from .corpus.mkobj import MACHINE, MkobjRefusal, build_object, find_call_targets
from .corpus.propagate_conventions import abi_key
from .inventory import BinaryView, pe_file_offset, pe_inventory
from .targets import TargetIdentity


SCHEMA = "agentdecompile.target-bound-source-hypothesis.v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def x86_32(architecture: str) -> bool:
    parts = architecture.split(":")
    arch = parts[0].lower()
    arch = "x86" if arch in {"i386", "x86_32"} else arch
    bits = parts[2] if len(parts) >= 3 else (64 if arch in {"x86_64", "amd64"} else 32)
    return abi_key("windows", "pe", arch, bits, architecture)[2:5] == ("x86", 32, "LE")


def recheck(identities: dict[Path, str]) -> None:
    for path, expected in identities.items():
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"Calibration input identity changed: {path}")


def pe_highlow_sites(view: BinaryView, pe: dict[str, Any]) -> list[int]:
    """Validate the entire PE32 relocation directory before certifying any slice."""
    if pe["machine"] != "0x014c" or pe["optionalHeaderMagic"] != "0x010b":
        raise ValueError("PE base relocation validation requires PE32 i386.")
    # pe_inventory retains a malformed optional-header observation as diagnostic
    # data. Do not let directory reads beyond its declared extent certify absence.
    coff = view.u32(0x3C) + 4
    optional = coff + 20
    optional_size = view.u16(coff + 16)
    directory_count = view.u32(optional + 92)
    if optional_size < 96 or directory_count > (optional_size - 96) // 8:
        raise ValueError("Malformed PE optional-header data-directory extent.")
    directories = pe["dataDirectories"]
    if len(directories) <= 5:
        return []
    directory = directories[5]
    rva, size = directory["rva"], directory["size"]
    if not rva and not size:
        return []
    if not rva or not size:
        raise ValueError("Malformed PE base relocation directory RVA/size.")
    offset = pe_file_offset(view, pe["sections"], rva, size, headers_size=pe["sizeOfHeaders"])
    cursor, limit, sites = offset, offset + size, []
    while cursor < limit:
        if limit - cursor < 8:
            raise ValueError("Malformed PE base relocation block header.")
        page, block_size = view.u32(cursor), view.u32(cursor + 4)
        if page % 4096 or block_size < 8 or block_size % 4 or block_size > limit - cursor:
            raise ValueError("Malformed PE base relocation block extent/alignment.")
        for position in range(cursor + 8, cursor + block_size, 2):
            entry = view.u16(position)
            kind, delta = entry >> 12, entry & 0xFFF
            if kind == 0:
                continue  # IMAGE_REL_BASED_ABSOLUTE padding has no fixup.
            if kind != 3:
                raise ValueError(f"Unsupported PE32 base relocation type: {kind}")
            site = page + delta
            pe_file_offset(view, pe["sections"], site, 4, headers_size=pe["sizeOfHeaders"])
            sites.append(site)
        cursor += block_size
    return sorted(sites)


def reject_relocation_overlap(sites: list[int], rva: int, size: int) -> None:
    first = bisect_left(sites, rva - 3)
    if first < len(sites) and sites[first] < rva + size:
        raise ValueError("Original function range overlaps a PE HIGHLOW base relocation.")


def prepare_probes(inventory: Path, receipt_path: Path, out_dir: Path,
                   fingerprint: str, architecture: str, max_cases: int) -> tuple[Path, dict[Path, str]]:
    """Preflight all inputs and construct only proven contiguous, reference-free slices."""
    from .source_parity_profile_corpus import select_cases

    inventory, receipt_path, out_dir = (p.expanduser().resolve() for p in (inventory, receipt_path, out_dir))
    inventory_data, receipt_data = inventory.read_bytes(), receipt_path.read_bytes()
    receipt = json.loads(receipt_data)
    if (receipt.get("schema") != "agentdecompile.original-target.v1"
            or receipt.get("state") != "ready"
            or receipt.get("authority") != "original-imported-executable"
            or receipt.get("analysisImageIsAuthority") is not False):
        raise ValueError("Probe bootstrap requires a ready original-target receipt with original executable authority.")
    if not fingerprint or receipt.get("programFingerprint") != fingerprint:
        raise ValueError("Probe program fingerprint does not match the original-target receipt.")
    if not x86_32(architecture):
        raise ValueError(f"Probe bootstrap requires x86 32-bit little-endian architecture: {architecture}")
    paths = {}
    for key in ("sourcePath", "targetPath"):
        value = receipt.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError(f"Original-target receipt lacks absolute {key}.")
        paths[key] = Path(value).resolve()
    source_data, target_data = (paths[key].read_bytes() for key in ("sourcePath", "targetPath"))
    target_hash = digest(target_data)
    if digest(source_data) != receipt.get("sourceSha256") or target_hash != receipt.get("targetSha256") or source_data != target_data:
        raise ValueError("Original executable source/copy bytes disagree with the target receipt.")
    identities = {inventory: digest(inventory_data), receipt_path: digest(receipt_data),
                  paths["sourcePath"]: digest(source_data), paths["targetPath"]: target_hash}
    analysis = receipt.get("analysisImagePath")
    analysis_hash = None
    if analysis:
        if not isinstance(analysis, str) or not Path(analysis).is_absolute():
            raise ValueError("Original-target receipt analysisImagePath must be absolute.")
        analysis_path = Path(analysis).resolve()
        analysis_hash = digest(analysis_path.read_bytes())
        identities[analysis_path] = analysis_hash
    producer_path = Path(__file__).resolve().parents[2] / "scripts/match-trivial.py"
    producer_data = producer_path.read_bytes()
    identities[producer_path] = digest(producer_data)
    # Match the existing script-module loading convention, but use snapshotted
    # definitions and never invoke the script's main or compilation path.
    spec = importlib.util.spec_from_file_location("agentdecompile_calibration_candidates", producer_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Candidate producer unavailable: {producer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(producer_data, str(producer_path), "exec"), module.__dict__)
    generation_key = digest(json.dumps({"inputs": {str(path): sha for path, sha in identities.items()},
                                        "fingerprint": fingerprint, "architecture": architecture,
                                        "maxCases": max_cases}, sort_keys=True).encode("utf-8"))
    generated = out_dir / "calibration-probes" / generation_key
    if not generated.resolve().is_relative_to(out_dir):
        raise ValueError("Generated probe directory escapes reserved out-dir through a symlink.")
    for path in identities:
        if path.is_relative_to(out_dir):
            raise ValueError(f"Calibration original input must be outside reserved out-dir: {path}")
    target = TargetIdentity(paths["sourcePath"], paths["targetPath"], target_hash,
                            len(target_data), "pe", "x86", target_hash, target_data)
    view = BinaryView(paths["targetPath"], target_data)
    pe = pe_inventory(target, view)
    if pe["machine"] != "0x014c" or pe["optionalHeaderMagic"] != "0x010b":
        raise ValueError("Original executable is not PE32 i386; architecture binding disagrees.")
    relocation_sites = pe_highlow_sites(view, pe)
    records, excluded = [], []
    for index, line in enumerate(inventory_data.decode("utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        try:
            # Legacy ExportFunctionInventory concatenates AddressSet bytes and
            # cannot certify continuity. Require the producer to expose ranges.
            ranges = row.get("bodyRanges")
            if not isinstance(ranges, list) or len(ranges) != 1:
                raise ValueError("missing single contiguous bodyRanges provenance")
            start, end = ranges[0]["start"], ranges[0]["endInclusive"]
            start = int(start, 16) if isinstance(start, str) else int(start)
            end = int(end, 16) if isinstance(end, str) else int(end)
            entry = row.get("entryOffset")
            if type(entry) is not int or entry != start:
                raise ValueError("body range does not begin at integer entryOffset")
            code = bytes.fromhex(row["bytes"])
            if not code or end - start + 1 != len(code) or row.get("bodyBytes") != len(code):
                raise ValueError("body range, byte count and inventory bytes disagree")
            offset = pe_file_offset(view, pe["sections"], start - pe["imageBase"], len(code))
            if view.bytes(offset, len(code)) != code:
                raise ValueError("inventory bytes differ from original executable range")
            reject_relocation_overlap(relocation_sites, start - pe["imageBase"], len(code))
            find_call_targets(code, MACHINE["coff-i386"], reference_free_only=True)
            name = f"probe_{start:08x}_{index}"
            candidate = module.candidate_for({**row, "name": name})
            if candidate is None:
                raise ValueError("no high-level source hypothesis")
            if candidate.extra_flags:
                raise ValueError(f"candidate extra_flags unsupported by common flag matrix: {candidate.extra_flags}")
            case_dir = generated / name
            records.append({"schema": SCHEMA, "hypothesis": True, "matched": False,
                            "name": name, "originalSymbol": row.get("name"), "entry": row.get("entry"),
                            "bodyBytes": len(code), "kind": candidate.kind, "outDir": str(case_dir),
                            "candidateSource": str(case_dir / "candidate.c"), "targetSymbol": candidate.symbol,
                            "programFingerprint": fingerprint, "architecture": architecture,
                            "targetReceipt": str(receipt_path), "targetReceiptSha256": identities[receipt_path],
                            "targetPath": str(paths["targetPath"]), "targetSha256": target_hash,
                            "analysisImagePath": analysis, "analysisImageSha256": analysis_hash,
                            "inventory": str(inventory), "inventorySha256": identities[inventory],
                            "inventoryRow": index + 1,
                            "producer": str(producer_path), "producerSha256": identities[producer_path],
                            "rangeStart": start, "rangeEndInclusive": end, "originalFileOffset": offset,
                            "originalBytesSha256": digest(code), "_probe_metadata": True})
        except (ValueError, KeyError, TypeError, MkobjRefusal) as exc:
            excluded.append({"row": index + 1, "name": row.get("name"), "reason": str(exc)})
    selected = select_cases(records, max_cases)
    if not selected:
        reasons = sorted({row["reason"] for row in excluded})
        raise ValueError("No corroborated relocation-free probe hypotheses: " + "; ".join(reasons))
    recheck(identities)
    manifest = generated / "hypotheses.jsonl"
    payloads = {}
    for row in selected:
        code = view.bytes(row["originalFileOffset"], row["bodyBytes"])
        candidate = module.candidate_for({"name": row["name"], "bytes": code.hex()})
        if candidate is None or candidate.extra_flags:
            raise ValueError("Selected hypothesis changed during bounded materialization.")
        obj = build_object(code, candidate.symbol, MACHINE["coff-i386"])
        if coff_functions(obj, prefix=candidate.symbol).get(candidate.symbol) != code:
            raise ValueError("emitted target symbol bytes differ from original range")
        source = candidate.source.encode("utf-8")
        row.pop("_probe_metadata")
        row.update(sourceSha256=digest(source), targetObjectSha256=digest(obj))
        payloads[Path(row["candidateSource"])] = source
        payloads[Path(row["outDir"]) / "target.obj"] = obj
    payloads[manifest] = "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected).encode("utf-8")
    payloads[generated / "excluded.json"] = (json.dumps(excluded, indent=2) + "\n").encode("utf-8")
    if generated.exists():
        for path, data in payloads.items():
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError(f"Conflicting or incomplete generated probe artifact: {path}")
        return manifest, identities
    generated.mkdir(parents=True)
    for path, data in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    return manifest, identities


def validate_bound_rows(rows: list[dict[str, Any]], fingerprint: str, architecture: str) -> dict[Path, str]:
    identities: dict[Path, str] = {}
    for row in rows:
        if row.get("schema") != SCHEMA or row.get("programFingerprint") != fingerprint or row.get("architecture") != architecture:
            raise ValueError("Measured admission requires target-bound hypotheses; legacy/global matches are diagnostic only.")
        required = ("targetReceipt", "targetReceiptSha256", "targetPath", "targetSha256", "inventory",
                    "inventorySha256", "producer", "producerSha256", "candidateSource", "sourceSha256",
                    "outDir", "targetObjectSha256", "rangeStart", "rangeEndInclusive", "originalFileOffset",
                    "originalBytesSha256", "targetSymbol", "inventoryRow")
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError("Bound probe lacks required provenance: " + ", ".join(missing))
        for path_key, hash_key in (("targetReceipt", "targetReceiptSha256"), ("targetPath", "targetSha256"),
                                   ("inventory", "inventorySha256"), ("producer", "producerSha256"),
                                   ("candidateSource", "sourceSha256")):
            identities[Path(row[path_key]).resolve()] = row[hash_key]
        identities[Path(row["outDir"]) / "target.obj"] = row["targetObjectSha256"]
        receipt = json.loads(Path(row["targetReceipt"]).read_bytes())
        if (receipt.get("schema") != "agentdecompile.original-target.v1"
                or receipt.get("state") != "ready"
                or receipt.get("authority") != "original-imported-executable"
                or receipt.get("analysisImageIsAuthority") is not False
                or receipt.get("programFingerprint") != fingerprint
                or receipt.get("targetSha256") != row["targetSha256"]
                or Path(receipt.get("targetPath", "")).resolve() != Path(row["targetPath"]).resolve()):
            raise ValueError("Probe target binding disagrees with original-target authority receipt.")
        origin = Path(receipt["sourcePath"]).resolve()
        identities[origin] = receipt["sourceSha256"]
        raw = Path(row["targetPath"]).read_bytes()
        if digest(raw) != receipt["sourceSha256"]:
            raise ValueError("Probe original source/copy digests disagree.")
        target = TargetIdentity(origin, Path(row["targetPath"]), row["targetSha256"],
                                len(raw), "pe", "x86", row["targetSha256"], raw)
        view = BinaryView(target.binary_path, raw)
        pe = pe_inventory(target, view)
        relocation_sites = pe_highlow_sites(view, pe)
        size = row["rangeEndInclusive"] - row["rangeStart"] + 1
        offset = pe_file_offset(view, pe["sections"], row["rangeStart"] - pe["imageBase"], size)
        code = view.bytes(offset, size)
        reject_relocation_overlap(relocation_sites, row["rangeStart"] - pe["imageBase"], size)
        inventory_lines = Path(row["inventory"]).read_text(encoding="utf-8").splitlines()
        observation = json.loads(inventory_lines[row["inventoryRow"] - 1])
        ranges = observation.get("bodyRanges")
        if not isinstance(ranges, list) or len(ranges) != 1:
            raise ValueError("Bound manifest inventory lacks single body range provenance.")
        def address(value: Any) -> int:
            return int(value, 16) if isinstance(value, str) else int(value)
        if (address(ranges[0]["start"]) != row["rangeStart"]
                or address(ranges[0]["endInclusive"]) != row["rangeEndInclusive"]
                or observation.get("entryOffset") != row["rangeStart"]
                or observation.get("bodyBytes") != size
                or bytes.fromhex(observation["bytes"]) != code):
            raise ValueError("Bound manifest disagrees with its function inventory range.")
        if (pe["machine"] != "0x014c" or offset != row["originalFileOffset"]
                or digest(code) != row["originalBytesSha256"]
                or coff_functions((Path(row["outDir"]) / "target.obj").read_bytes(),
                                  prefix=row["targetSymbol"]).get(row["targetSymbol"]) != code):
            raise ValueError("Bound probe target symbol does not reproduce its original executable range.")
        find_call_targets(code, MACHINE["coff-i386"], reference_free_only=True)
        analysis = receipt.get("analysisImagePath")
        declared_analysis = row.get("analysisImagePath")
        if bool(analysis) != bool(declared_analysis):
            raise ValueError("Probe analysis-image provenance is omitted or substituted.")
        if analysis:
            if (not isinstance(analysis, str) or not Path(analysis).is_absolute()
                    or not isinstance(declared_analysis, str) or not Path(declared_analysis).is_absolute()
                    or Path(analysis).resolve() != Path(declared_analysis).resolve()):
                raise ValueError("Probe analysis-image path disagrees with original-target receipt.")
            expected_analysis_hash = row.get("analysisImageSha256")
            if not isinstance(expected_analysis_hash, str) or len(expected_analysis_hash) != 64:
                raise ValueError("Probe analysis-image provenance lacks SHA256.")
            identities[Path(analysis).resolve()] = expected_analysis_hash
        elif row.get("analysisImageSha256") is not None:
            raise ValueError("Probe invents analysis-image digest absent from original-target receipt.")
    recheck(identities)
    return identities
