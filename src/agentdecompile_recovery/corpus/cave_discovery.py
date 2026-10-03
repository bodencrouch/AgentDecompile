"""Scan static candidates for consistency with declared image-bound evidence.

All coordinates supplied here are raw file offsets, with half-open ranges. The
existing asm_extent decoder only qualifies narrow PE32 function extents; it does
not produce complete relocation/data-reference exclusions for whole images.
Accordingly the ordinary pack exporter reports that missing prerequisite rather
than treating executable padding as safe memory.
"""
from __future__ import annotations

import hashlib


def discovery_blocker(build: str) -> dict:
    return {"build": build, "status": "blocked", "reason": "complete_decode_evidence_unavailable",
            "missing": ["complete_instruction_ranges", "relocation_ranges", "data_reference_targets",
                        "decoded_function_ends", "unique_tail_anchors"],
            "available_decoder": "corpus.asm_extent.decode (bounded PE32 i386 only)",
            "next": "Capture complete image-bound decode and exclusion evidence before cave discovery"}


def discover_caves(image: bytes, *, build: str, arch: str, evidence: dict,
                   min_capacity: int = 8, filler_bytes=(0, 0x90, 0xCC)) -> list[dict]:
    """Return static plan templates, never claims of live allocation permission.

    evidence carries image_sha256, decoder identity, complete=True,
    executable_sections/instructions/relocations as (start,end) pairs,
    data_references as offsets, function_ends as decoded end offsets, and
    anchors [{key,offset,expected_bytes,margin,required_margin}]. A caller must
    independently qualify the evidence producer; this routine validates its
    internal coordinate and byte consistency, not producer trust.
    """
    if not isinstance(image, bytes) or not image:
        raise ValueError("image_bytes_required")
    if type(min_capacity) is not int or min_capacity < 1:
        raise ValueError("invalid_min_capacity")
    if not isinstance(evidence, dict) or evidence.get("complete") is not True:
        raise ValueError("complete_decode_evidence_required")
    digest = hashlib.sha256(image).hexdigest()
    if evidence.get("image_sha256") != digest or not evidence.get("decoder"):
        raise ValueError("decode_image_or_decoder_identity_mismatch")
    required = {"executable_sections", "instructions", "relocations", "data_references", "function_ends", "anchors"}
    if not required <= evidence.keys():
        raise ValueError("decode_exclusion_evidence_incomplete")
    def ranges(name):
        result = []
        for pair in evidence[name]:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("invalid_" + name)
            start, end = pair
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(image):
                raise ValueError("invalid_" + name)
            result.append((start, end))
        return sorted(result)
    sections = ranges("executable_sections")
    if any(right[0] < left[1] for left, right in zip(sections, sections[1:])):
        raise ValueError("overlapping_executable_sections")
    instructions, relocations = ranges("instructions"), ranges("relocations")
    if not sections or not instructions:
        raise ValueError("decoded_executable_ranges_required")
    ends = sorted(set(evidence["function_ends"]))
    refs = set(evidence["data_references"])
    if any(type(v) is not int or not 0 <= v <= len(image) for v in ends):
        raise ValueError("invalid_function_end")
    if any(type(v) is not int or not 0 <= v < len(image) for v in refs):
        raise ValueError("invalid_data_reference")
    if any(end not in {r[1] for r in instructions} for end in ends):
        raise ValueError("function_end_not_decoded")
    anchors = []
    for anchor in evidence["anchors"]:
        at = anchor.get("offset")
        try:
            pattern = bytes.fromhex(anchor.get("expected_bytes", ""))
        except (TypeError, ValueError):
            raise ValueError("invalid_anchor_bytes") from None
        if type(at) is not int or at < 0 or not pattern or image[at:at + len(pattern)] != pattern:
            continue
        # Overlapping hits count too; bytes.count would miss those.
        first = image.find(pattern)
        if first != at or image.find(pattern, at + 1) != -1:
            continue
        margin, needed = anchor.get("margin"), anchor.get("required_margin")
        if type(margin) is not int or type(needed) is not int or needed < 1 or margin < needed:
            continue
        if not anchor.get("key") or at + len(pattern) not in ends:
            continue
        if not any(start <= at and at + len(pattern) <= end for start, end in sections):
            continue
        anchors.append((at, pattern, anchor))
    fillers = set(filler_bytes)
    if any(type(v) is not int or not 0 <= v <= 255 for v in fillers):
        raise ValueError("invalid_filler_byte")
    output = []
    for section_start, section_end in sections:
        cursor = section_start
        while cursor < section_end:
            start = cursor
            value = image[cursor]
            cursor += 1
            while cursor < section_end and image[cursor] == value:
                cursor += 1
            end = cursor
            if value not in fillers or end - start < min_capacity:
                continue
            if any(a < end and b > start for a, b in instructions + relocations):
                continue
            if any(start <= reference < end for reference in refs):
                continue
            before = [at for at in ends if section_start <= at <= start]
            after = [at for at in ends if end <= at <= section_end]
            if not before or not after or max(before) == min(after):
                continue
            eligible = [(at, pattern, anchor) for at, pattern, anchor in anchors
                        if section_start <= at and at + len(pattern) <= section_end]
            if not eligible:
                continue
            at, pattern, anchor = min(eligible, key=lambda a: (abs(start - (a[0] + len(a[1]))), a[0], a[2]["key"]))
            original = image[start:end].hex().upper()
            cave_id = hashlib.sha256(f"{digest}:{start}:{end}:{anchor['key']}".encode()).hexdigest()
            output.append({"id": cave_id, "build": build, "arch": arch,
                "claim": {"cave_id": cave_id, "build_sha256": digest},
                "anchor": {"kind": "masked_window", "key": anchor["key"], "value": pattern.hex().upper(),
                           "mask": "FF" * len(pattern), "portable": True,
                           "uniqueness": {"scope": "whole_image", "hits": 1, "margin": anchor["margin"]}},
                "offset": start - at, "capacity": end - start, "original_bytes": original,
                "relocation_rules": {"observed_relocations": [], "emitted_code": "requires_architecture_adapter"},
                "restoration": {"original_bytes": original, "verify_before_install": True,
                                "verify_after_restore": True, "release_requires_quiescence": True},
                "coverage": [{"build": build, "status": "pinned", "capacity": end - start,
                              "reason": "Static candidate only; live preflight, adapter and ownership required"}],
                "live_allocation_allowed": False})
    return sorted(output, key=lambda c: (c["anchor"]["key"], -c["capacity"], c["offset"], c["id"]))
