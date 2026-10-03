"""Recorded embedded target names, independent of corpus identity labels.

PE export and thin Mach-O N_FUN claims have distinct scopes. This module neither
establishes cross-build identity nor validates compilation or linked images.
Callers pass candidates admitted by the source/target/raw-region ingress gates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..inventory import BinaryView, InventoryError, build_binary_inventory, pe_file_offset
from ..targets import identify_binary
from .macho_semantic_witness import (
    FAT_MAGICS, WitnessError, normalise_arch, observe_snapshot, region_offset,
)
from .machostabs import CPU_NAMES, _split_stabs_decl

CLAIM_SCOPE = "target-pe-export-name-at-va-v1"
ACCEPTED = "accepted-target-pe-export"
STABS_CLAIM_SCOPE = "target-macho-stabs-n-fun-name-at-va-v1"
STABS_ACCEPTED = "accepted-target-macho-stabs-n-fun"
STABS_REASON = "accepted_unique_embedded_n_fun"
LOCAL_ONLY = "target-local-only"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def observe_target(binary: dict, raw_dir: Path | None) -> dict:
    """Read one frozen image; all name rows and its hash describe those bytes."""
    target = {"binaryId": binary.get("id"), "slug": binary.get("slug"), "sha256": None}
    result = {"target": target, "exports": [], "reason": None}
    if raw_dir is None or not binary.get("slug"):
        result["reason"] = "target_unavailable"
        return result
    try:
        identity = identify_binary(Path(raw_dir) / binary["slug"], retain_snapshot=True)
        target.update(sha256=identity.sha256, format=identity.format)
        if identity.format == "macho" or identity.snapshot[:4] in FAT_MAGICS:
            target["format"] = "macho"
            result["claimScope"] = STABS_CLAIM_SCOPE
            try:
                macho = observe_snapshot(identity.snapshot, binary)
            except WitnessError as exc:
                result["reason"] = str(exc)
                return result
            result.update(macho)
            target.update({key: macho[key] for key in ("architecture", "selectedArchitecture", "slice")})
            return result
        if identity.format != "pe":
            result["reason"] = "unsupported_target_format"
            return result
        inventory = build_binary_inventory(identity)
        observation = inventory.get("exportObservation", {})
        if (inventory.get("format") != "pe" or inventory.get("target", {}).get("sha256") != identity.sha256
                or observation.get("status") != "complete" or type(inventory.get("imageBase")) is not int):
            result["reason"] = "malformed_target_inventory"
            return result
        target["imageBase"] = inventory["imageBase"]
        result["exports"] = observation["exports"]
        result["view"] = BinaryView(identity.binary_path, identity.snapshot)
        result["sections"] = inventory["sections"]
        result["headersSize"] = inventory["sizeOfHeaders"]
    except OSError:
        result["reason"] = "target_unavailable"
    except (InventoryError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        result["reason"] = ("malformed_macho_stabs_inventory" if result.get("claimScope") == STABS_CLAIM_SCOPE
                            else "malformed_target_inventory")
    return result


def evaluate_candidate(candidate: dict, binary: dict, observation: dict) -> dict:
    """Evaluate a previously validated address-local candidate against a snapshot."""
    if observation.get("claimScope") == STABS_CLAIM_SCOPE:
        return _evaluate_stabs_candidate(candidate, binary, observation)
    target = observation["target"]
    name, address = candidate.get("name"), candidate.get("addr")
    evidence = {"schema": "agentdecompile.target-symbol-witness.v1", "claimScope": CLAIM_SCOPE,
                "target": target, "claim": {"name": name, "address": address}}
    digest = target.get("sha256")
    corpus_digest = binary.get("content_sha256")
    reason = observation.get("reason")
    # Digest agreement always precedes any assertion about target-side names.
    if not corpus_digest:
        reason = "missing_corpus_target_digest"
    elif digest and corpus_digest != digest:
        reason = "corpus_target_digest_mismatch"
    elif digest and candidate.get("target_sha256") != digest:
        reason = "candidate_target_digest_mismatch"
    elif not reason and (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
        reason = "malformed_target_inventory"
    elif not reason and (not isinstance(name, str) or not name):
        reason = "claimed_name_missing"
    elif not reason and type(address) is not int:
        reason = "claimed_address_invalid"
    if not reason:
        # A real ordinal_12 name is admissible; synthetic display labels are not.
        matches = [row for row in observation["exports"] if row.get("nameRva") is not None and row.get("name") == name]
        if not matches:
            reason = "target_export_missing"
        elif len(matches) != 1:
            reason = "target_export_ambiguous"
        else:
            row = matches[0]
            va = target["imageBase"] + row["rva"]
            if row.get("forwarded") is not False:
                reason = "target_export_forwarded"
            elif va != address:
                reason = "target_export_address_mismatch"
            else:
                try:
                    data = bytes.fromhex(candidate.get("machine_code") or "")
                    size = candidate.get("size")
                    if type(size) is not int or size <= 0 or len(data) != size:
                        raise ValueError("missing candidate region")
                    offset = pe_file_offset(observation["view"], observation["sections"], row["rva"], size,
                                            headers_size=observation["headersSize"])
                    if candidate.get("target_offset") != offset or observation["view"].bytes(offset, size) != data:
                        raise ValueError("candidate region does not map to export")
                except (ValueError, TypeError, KeyError):
                    reason = "candidate_target_region_mismatch"
                if not reason:
                    evidence["witness"] = {"source": "embedded-pe-export-directory", "name": name,
                                       "ordinal": row["ordinal"], "nameRva": row["nameRva"],
                                       "nameTableIndex": row["hint"], "rva": row["rva"], "va": va,
                                       "forwarded": False}
    status = LOCAL_ONLY if reason else ACCEPTED
    evidence["reason"] = reason or "accepted_unique_nonforwarded_export"
    return {"semantic_status": status, "semantic_reason": evidence["reason"],
            "semantic_evidence": json.dumps(evidence, sort_keys=True)}


def _evaluate_stabs_candidate(candidate: dict, binary: dict, observation: dict) -> dict:
    target = observation["target"]
    name, address = candidate.get("name"), candidate.get("addr")
    evidence = {"schema": "agentdecompile.target-symbol-witness.v1", "claimScope": STABS_CLAIM_SCOPE,
                "target": target, "claim": {"name": name, "address": address}}
    digest = target.get("sha256")
    reason = observation.get("reason")
    if not binary.get("content_sha256"):
        reason = "missing_corpus_target_digest"
    elif digest and binary["content_sha256"] != digest:
        reason = "corpus_target_digest_mismatch"
    elif digest and candidate.get("target_sha256") != digest:
        reason = "candidate_target_digest_mismatch"
    elif not reason and (candidate.get("binary_id") != target.get("binaryId") or binary.get("id") != target.get("binaryId")):
        reason = "candidate_target_binary_mismatch"
    elif not reason and (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
        reason = "malformed_macho_stabs_inventory"
    elif not reason and (not isinstance(name, str) or not name):
        reason = "claimed_name_missing"
    elif not reason and (type(address) is not int or address < 0):
        reason = "claimed_address_invalid"
    if not reason:
        matches = [row for row in observation["stabs"] if row["name"] == name]
        at_va = [row for row in observation["stabs"] if row["va"] == address]
        if not matches:
            reason = "target_stabs_name_missing"
        elif len(matches) != 1:
            reason = "target_stabs_name_ambiguous"
        elif matches[0]["va"] != address:
            reason = "target_stabs_address_mismatch"
        elif len(at_va) != 1:
            reason = "target_stabs_address_ambiguous"
        else:
            try:
                data = bytes.fromhex(candidate.get("machine_code") or "")
                size = candidate.get("size")
                if type(size) is not int or size <= 0 or len(data) != size:
                    raise ValueError("missing candidate region")
                offset = region_offset(observation, address, size)
                if (type(candidate.get("target_offset")) is not int or candidate["target_offset"] != offset
                        or observation["snapshot"][offset:offset + size] != data):
                    raise ValueError("candidate region does not map to N_FUN")
            except (ValueError, TypeError, KeyError):
                reason = "candidate_target_region_mismatch"
            if not reason:
                evidence["witness"] = {**matches[0], "source": "embedded-macho-stabs-n-fun",
                                       "targetSha256": digest, "binaryId": target["binaryId"],
                                       "architecture": target["architecture"], "slice": target["slice"],
                                       "symbolTable": observation["symbolTable"],
                                       "region": {"address": address, "offset": offset, "size": size}}
    evidence["reason"] = reason or STABS_REASON
    return {"semantic_status": LOCAL_ONLY if reason else STABS_ACCEPTED, "semantic_reason": evidence["reason"],
            "semantic_evidence": json.dumps(evidence, sort_keys=True)}


def bind_candidates(con, candidates: list[dict], raw_dir: Path | None) -> None:
    """Common ordinary/seed ingress; failed names never remove local candidates."""
    has_binary = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='binary'").fetchone()
    binaries = {row["id"]: dict(row) for row in con.execute("SELECT * FROM binary")} if has_binary else {}
    # Cache only within this admission call; never reuse a previous file observation.
    observations: dict[tuple[int | None, str | None], dict] = {}
    observed_keys: dict[int | None, tuple[int | None, str | None]] = {}
    for candidate in candidates:
        bid = candidate.get("binary_id")
        binary = binaries.get(bid, {})
        if bid not in observed_keys:
            observation = observe_target(binary, raw_dir)
            key = (bid, observation["target"].get("sha256"))
            observations[key] = observation
            observed_keys[bid] = key
        candidate.update(evaluate_candidate(candidate, binary, observations[observed_keys[bid]]))


def recorded_export_name(row: dict) -> str | None:
    """Read a coherent recorded witness; this does not recheck target currentness."""
    if row.get("semantic_status") != ACCEPTED or row.get("semantic_reason") != "accepted_unique_nonforwarded_export":
        return None
    try:
        evidence = json.loads(row.get("semantic_evidence") or "null")
        target, claim, witness = evidence["target"], evidence["claim"], evidence["witness"]
        digest = row.get("target_sha256")
        if (evidence["schema"] == "agentdecompile.target-symbol-witness.v1" and evidence["claimScope"] == CLAIM_SCOPE
                and isinstance(digest, str) and _DIGEST.fullmatch(digest) and target["sha256"] == digest
                and target["binaryId"] == row.get("binary_id") and target["format"] == "pe"
                and witness["source"] == "embedded-pe-export-directory" and witness["forwarded"] is False
                and type(witness["nameRva"]) is int and type(witness["rva"]) is int
                and type(target["imageBase"]) is int and type(row.get("addr")) is int
                and witness["va"] == target["imageBase"] + witness["rva"] == claim["address"] == row["addr"]
                and isinstance(witness["name"], str) and witness["name"]
                and witness["name"] == claim["name"] == row.get("name")):
            return witness["name"]
    except (ValueError, TypeError, KeyError):
        pass
    return None


def recorded_stabs_name(row: dict) -> str | None:
    """Check recorded internal bindings only; never promote attribution or edges."""
    if row.get("semantic_status") != STABS_ACCEPTED or row.get("semantic_reason") != STABS_REASON:
        return None
    try:
        evidence = json.loads(row.get("semantic_evidence") or "null")
        target, claim, witness = evidence["target"], evidence["claim"], evidence["witness"]
        digest = row.get("target_sha256")
        architecture, slice_ = target["architecture"], target["slice"]
        table, region = witness["symbolTable"], witness["region"]
        cpu, subtype, bits = architecture["cpuType"], architecture["cpuSubtype"], architecture["bits"]
        integer_fields = [slice_["offset"], slice_["size"], table["commandEnd"], table["offset"], table["count"],
                          table["recordSize"], table["stringOffset"], table["stringSize"],
                          witness["nlistIndex"], witness["recordOffset"], witness["stringIndex"],
                          witness["stringOffset"], witness["stringEnd"], witness["rawType"],
                          witness["va"], claim["address"], row.get("addr"), region["address"],
                          region["offset"], region["size"]]
        if (evidence["schema"] != "agentdecompile.target-symbol-witness.v1"
                or evidence["claimScope"] != STABS_CLAIM_SCOPE or evidence["reason"] != STABS_REASON
                or not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
                or target["sha256"] != digest or witness["targetSha256"] != digest
                or any(type(value) is not int for value in (row.get("binary_id"), target["binaryId"], witness["binaryId"]))
                or target["binaryId"] != row.get("binary_id") or witness["binaryId"] != row.get("binary_id")
                or target["format"] != "macho" or witness["source"] != "embedded-macho-stabs-n-fun"
                or witness["architecture"] != architecture or witness["slice"] != slice_
                or type(cpu) is not int or type(subtype) is not int or not -(1 << 31) <= subtype < 1 << 31
                or type(bits) is not int or bits not in (32, 64) or (bits == 64) != bool(cpu & 0x01000000)
                or CPU_NAMES.get(cpu) != architecture["name"] or normalise_arch(architecture["name"]) is None
                or target["selectedArchitecture"] != architecture["name"]
                or architecture["endianness"] not in ("little", "big")
                or any(type(value) is not int for value in integer_fields)):
            return None
        name, declaration = witness["name"], witness["declaration"]
        if (slice_["offset"] != 0 or slice_["size"] <= 0 or witness["rawType"] != 0x24
                or not 0 <= witness["nlistIndex"] < table["count"]
                or table["recordSize"] != (16 if bits == 64 else 12)
                or not (32 if bits == 64 else 28) <= table["commandEnd"] <= slice_["size"]
                or table["offset"] < table["commandEnd"]
                or table["offset"] + table["count"] * table["recordSize"] > slice_["size"]
                or table["stringOffset"] < table["commandEnd"] or table["stringSize"] <= 0
                or table["stringOffset"] + table["stringSize"] > slice_["size"]
                or (table["offset"] < table["stringOffset"] + table["stringSize"]
                    and table["stringOffset"] < table["offset"] + table["count"] * table["recordSize"])
                or witness["recordOffset"] != table["offset"] + witness["nlistIndex"] * table["recordSize"]
                or not 0 < witness["stringIndex"] < table["stringSize"]
                or witness["stringOffset"] != table["stringOffset"] + witness["stringIndex"]
                or not witness["stringOffset"] < witness["stringEnd"] < table["stringOffset"] + table["stringSize"]
                or not isinstance(name, str) or not name or not isinstance(declaration, str)
                or "\0" in declaration or _split_stabs_decl(declaration)[0] != name
                or len(declaration.encode("utf-8")) != witness["stringEnd"] - witness["stringOffset"]
                or name != claim["name"] or name != row.get("name")
                or not witness["va"] == claim["address"] == row["addr"] == region["address"]
                or witness["va"] < 0 or region["offset"] < 0 or region["size"] <= 0
                or region["offset"] + region["size"] > slice_["size"]
                or region["address"] + region["size"] > 1 << bits
                or (row.get("size") is not None and (type(row["size"]) is not int or row["size"] != region["size"]))):
            return None
        return name
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def recorded_name_witness(row: dict) -> dict | None:
    """Dispatch only qualified scopes, retaining PE-only reader compatibility."""
    name = recorded_export_name(row)
    if name is not None:
        return {"name": name, "claimScope": CLAIM_SCOPE, "kind": "PE Export"}
    name = recorded_stabs_name(row)
    if name is not None:
        return {"name": name, "claimScope": STABS_CLAIM_SCOPE, "kind": "Mach-O STABS N_FUN"}
    return None


def recorded_target_name(row: dict) -> str | None:
    witness = recorded_name_witness(row)
    return witness["name"] if witness is not None else None
